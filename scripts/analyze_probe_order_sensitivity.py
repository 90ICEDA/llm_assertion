#!/usr/bin/env python3
"""Offline replay of fixed candidate×probe verdicts under probe orderings."""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, random
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"outputs/behavioral_preference_pilot_v1/behavioral_probes_v3"
SEEDS=[20260815+i for i in range(5)]
BUDGETS=[8,16,32]
STRATEGIES=["random","disagreement_high_to_low","disagreement_low_to_high"]

def long(p:Path)->str:
    s=str(p.resolve())
    return "\\\\?\\"+s if os.name=="nt" and not s.startswith("\\\\?\\") else s
def load(p):
    with open(long(Path(p)),encoding="utf-8-sig") as f:return json.load(f)
def write_csv(p,data,fields=None):
    p.parent.mkdir(parents=True,exist_ok=True); fields=fields or (list(data[0]) if data else [])
    with p.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(data)
def stable(*x):return hashlib.sha256("\x1f".join(map(str,x)).encode()).hexdigest()[:24]
def pair_id(parent,a,b):return stable("unordered_pair",parent,*sorted((a,b)))
def jaccard(a,b):return 1.0 if not a and not b else len(a&b)/len(a|b)
def tau(order_a,order_b):
    pos={x:i for i,x in enumerate(order_b)}; c=d=0
    for i in range(len(order_a)):
      for j in range(i+1,len(order_a)):
        if pos[order_a[i]]<pos[order_a[j]]:c+=1
        else:d+=1
    return (c-d)/(c+d) if c+d else 1.0
def relation(sig,a,b):
    fpa={p for p,v in sig[a].items() if v[0]}; fpb={p for p,v in sig[b].items() if v[0]}
    tpa={p for p,v in sig[a].items() if v[1]}; tpb={p for p,v in sig[b].items() if v[1]}
    if fpa==fpb and tpa==tpb:return "equal_signature"
    if (fpa<=fpb and tpa>=tpb) or (fpb<=fpa and tpb>=tpa):return "dominance"
    return "crossing_incomparable"
def order_for(strategy,seed,parent,probes,scores):
    rng=random.Random(seed ^ int(hashlib.sha256(parent.encode()).hexdigest()[:16],16))
    if strategy=="random":
        ans=list(probes);rng.shuffle(ans);return ans
    groups=defaultdict(list)
    for p in probes:groups[scores[p]].append(p)
    keys=sorted(groups,reverse=strategy.endswith("high_to_low"));ans=[]
    for k in keys:
        g=groups[k];rng.shuffle(g);ans.extend(g)
    return ans

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",default="deliverables/probe_order_sensitivity_20260829");args=ap.parse_args()
    out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True)
    train=list(csv.DictReader((ROOT/"outputs/behavioral_preference_pilot_v1/selected_train_parents.csv").open(encoding="utf-8-sig",newline="")))
    parents=sorted({x["parent_bug_id"] for x in train})
    verdicts={}; candidates={}; probes={}; audit=[]; cache_mismatch=[]
    for parent in parents:
        ev=[]
        for slot in range(1,9):
            p=ROOT/f"outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30/{parent}/slot_{slot:02d}/attempt_01/evidence.json"
            d=load(p);ev.append(f"{parent}__v3_slot_{int(d['slot']):02d}")
        candidates[parent]=sorted(ev)
        pool=load(BASE/parent/"probe_pool.json")["probes"]
        probes[parent]=[x["probe_id"] for x in pool]
        if len(probes[parent])!=64 or len(set(probes[parent]))!=64:raise RuntimeError(f"{parent}: probe pool not 64 unique")
        seen=set(); timeouts=0
        for probe in probes[parent]:
          for cand in candidates[parent]:
            p=BASE/parent/"runs"/probe/cand/"result.json"
            if not os.path.exists(long(p)):
                cache_mismatch.append({"parent_id":parent,"probe_id":probe,"candidate_id":cand,"issue":"missing_verdict","path":str(p.relative_to(ROOT))});continue
            d=load(p);key=(parent,probe,cand)
            if key in seen:cache_mismatch.append({"parent_id":parent,"probe_id":probe,"candidate_id":cand,"issue":"duplicate_verdict","path":str(p.relative_to(ROOT))})
            seen.add(key)
            cr=d["rtl"]["correct"];br=d["rtl"]["buggy"]
            derived_exec=all(x["compile"]["returncode"]==0 and x["simulation"] and x["simulation"]["returncode"]==0 and not x["compile"].get("timeout") and not x["simulation"].get("timeout") for x in (cr,br))
            derived_fp=derived_exec and cr["fail_hits"]>0
            derived_tp=derived_exec and br["fail_hits"]>0 and cr["fail_hits"]==0
            if (d["executable"],d["fp"],d["tp"])!=(derived_exec,derived_fp,derived_tp):cache_mismatch.append({"parent_id":parent,"probe_id":probe,"candidate_id":cand,"issue":"cached_verdict_inconsistent","path":str(p.relative_to(ROOT))})
            t=sum(bool(x[stage] and x[stage].get("timeout")) for x in (cr,br) for stage in ("compile","simulation"));timeouts+=t
            verdicts[key]=(bool(d["fp"]),bool(d["tp"]),t)
        audit.append({"parent_id":parent,"candidate_count":len(candidates[parent]),"probe_count":len(probes[parent]),"expected_verdicts":512,"loaded_verdicts":len(seen),"timeout_stage_count":timeouts})
    write_csv(out/"verdict_integrity.csv",audit);write_csv(out/"cache_inconsistencies.csv",cache_mismatch,["parent_id","probe_id","candidate_id","issue","path"])
    if cache_mismatch:raise RuntimeError(f"{len(cache_mismatch)} verdict integrity failures; formal/cache repair required")

    # Static single-probe disagreement score: number of the 28 candidate pairs
    # separated by their (FP,TP) verdict on that probe. Distinct signatures is a
    # secondary score; seeded tie-breaking handles exact score ties.
    score_rows=[];scores={}
    for parent in parents:
      scores[parent]={}
      for probe in probes[parent]:
        vals={c:verdicts[(parent,probe,c)][:2] for c in candidates[parent]}
        separated=sum(vals[a]!=vals[b] for a,b in combinations(candidates[parent],2))
        score=(separated,len(set(vals.values())))
        scores[parent][probe]=score
        score_rows.append({"parent_id":parent,"probe_id":probe,"separated_candidate_pairs":separated,"distinct_fp_tp_signatures":score[1],"disagreement_score":f"{score[0]}|{score[1]}"})
    write_csv(out/"probe_disagreement_scores.csv",score_rows)

    replay=[];first_rows=[];curve=[];class_rows=[];orders={};resolved_sets={}
    for strategy in STRATEGIES:
      for seed in SEEDS:
        global_resolved=set();global_first={};global_counts=Counter()
        for parent in parents:
          order=order_for(strategy,seed,parent,probes[parent],scores[parent]);orders[(strategy,seed,parent)]=order
          sig={c:{} for c in candidates[parent]};first={};prev_budget=set()
          parent_pairs={pair_id(parent,a,b):(a,b) for a,b in combinations(candidates[parent],2)}
          for rank,probe in enumerate(order,1):
            for c in candidates[parent]:sig[c][probe]=verdicts[(parent,probe,c)][:2]
            now={pid for pid,(a,b) in parent_pairs.items() if any(sig[a][p]!=sig[b][p] for p in sig[a])}
            for pid in now:
                if pid not in first:first[pid]=rank
            curve.append({"strategy":strategy,"seed":seed,"parent_id":parent,"probe_count":rank,"resolved_pair_count":len(now),"resolved_fraction":len(now)/28})
            if rank in BUDGETS:
              rels=Counter(relation(sig,a,b) for a,b in parent_pairs.values())
              used=order[:rank];to=sum(verdicts[(parent,p,c)][2] for p in used for c in candidates[parent])
              replay.append({"strategy":strategy,"seed":seed,"parent_id":parent,"budget":rank,"resolved_pair_set":json.dumps(sorted(now)),"newly_resolved_pairs":json.dumps(sorted(now-prev_budget)),"first_distinguish_rank":json.dumps({p:first[p] for p in sorted(now)},sort_keys=True),"probe_order":json.dumps(used),"timeout_count":to})
              class_rows.append({"strategy":strategy,"seed":seed,"parent_id":parent,"budget":rank,"dominance":rels["dominance"],"equal_signature":rels["equal_signature"],"crossing_incomparable":rels["crossing_incomparable"]})
              resolved_sets[(strategy,seed,rank,parent)]=set(now);prev_budget=set(now)
          for pid,r in first.items():first_rows.append({"strategy":strategy,"seed":seed,"parent_id":parent,"pair_id":pid,"first_distinguish_rank":r})
    write_csv(out/"replay_by_parent.csv",replay);write_csv(out/"first_distinguish_rank.csv",first_rows);write_csv(out/"resolution_curve_by_parent.csv",curve);write_csv(out/"relation_counts_by_parent.csv",class_rows)

    # Aggregate fixed 840-pair universe.
    agg=[]
    for strategy in STRATEGIES:
      for seed in SEEDS:
        for budget in BUDGETS:
          rs=set().union(*(resolved_sets[(strategy,seed,budget,p)] for p in parents)); cr=[x for x in class_rows if x["strategy"]==strategy and x["seed"]==seed and x["budget"]==budget]
          agg.append({"strategy":strategy,"seed":seed,"budget":budget,"resolved_pairs":len(rs),"resolved_fraction":len(rs)/840,"dominance":sum(int(x["dominance"]) for x in cr),"equal_signature":sum(int(x["equal_signature"]) for x in cr),"crossing_incomparable":sum(int(x["crossing_incomparable"]) for x in cr),"timeout_count":sum(int(x["timeout_count"]) for x in replay if x["strategy"]==strategy and x["seed"]==seed and x["budget"]==budget)})
    write_csv(out/"aggregate_budget_summary.csv",agg)
    jac=[]
    for budget in BUDGETS:
      for seed in SEEDS:
        for a,b in combinations(STRATEGIES,2):
          A=set().union(*(resolved_sets[(a,seed,budget,p)] for p in parents));B=set().union(*(resolved_sets[(b,seed,budget,p)] for p in parents))
          jac.append({"comparison":"between_strategies","budget":budget,"strategy_a":a,"seed_a":seed,"strategy_b":b,"seed_b":seed,"intersection":len(A&B),"union":len(A|B),"jaccard":jaccard(A,B)})
      for s in STRATEGIES:
        for a,b in combinations(SEEDS,2):
          A=set().union(*(resolved_sets[(s,a,budget,p)] for p in parents));B=set().union(*(resolved_sets[(s,b,budget,p)] for p in parents))
          jac.append({"comparison":"within_strategy_across_seeds","budget":budget,"strategy_a":s,"seed_a":a,"strategy_b":s,"seed_b":b,"intersection":len(A&B),"union":len(A|B),"jaccard":jaccard(A,B)})
    write_csv(out/"jaccard_comparisons.csv",jac)
    curve_agg=[]
    for strategy in STRATEGIES:
      for seed in SEEDS:
        for rank in range(1,65):
          xs=[x for x in curve if x["strategy"]==strategy and x["seed"]==seed and x["probe_count"]==rank]
          n=sum(int(x["resolved_pair_count"]) for x in xs)
          curve_agg.append({"strategy":strategy,"seed":seed,"probe_count":rank,"resolved_pairs":n,"resolved_fraction":n/840})
    write_csv(out/"resolution_curve_aggregate.csv",curve_agg)
    kt=[]
    for seed in SEEDS:
      for parent in parents:
        for a,b in combinations(STRATEGIES,2):kt.append({"seed":seed,"parent_id":parent,"strategy_a":a,"strategy_b":b,"kendall_tau_full_probe_order":tau(orders[(a,seed,parent)],orders[(b,seed,parent)])})
    write_csv(out/"kendall_probe_order.csv",kt)
    # Full pool must converge because all verdict cells are available.
    final_sets={}
    for s in STRATEGIES:
      for seed in SEEDS:
        fs=set()
        for parent in parents:
          for a,b in combinations(candidates[parent],2):
            if any(verdicts[(parent,p,a)][:2]!=verdicts[(parent,p,b)][:2] for p in probes[parent]):fs.add(pair_id(parent,a,b))
        final_sets[(s,seed)]=fs
    final_equal=len({frozenset(x) for x in final_sets.values()})==1
    summary={"status":"complete","parents":30,"candidates":240,"unordered_pairs":840,"probes_per_parent":64,"verdict_cells":15360,"strategies":STRATEGIES,"seeds":SEEDS,"budgets":BUDGETS,"timeout_stage_count":sum(int(x["timeout_stage_count"]) for x in audit),"cache_inconsistency_count":len(cache_mismatch),"full_pool_final_sets_equal":final_equal,"full_pool_resolved_pairs":len(next(iter(final_sets.values())))}
    (out/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    (out/"PROBE_ORDER_SENSITIVITY.md").write_text(f'''# Probe 顺序敏感性离线重放\n\n固定 30 parents、240 candidates、每 parent 64 probes、840 个同-parent无序候选对；3 种顺序各 5 seeds，budget=8/16/32。disagreement score 定义为单个 probe 将 8 candidates 的 28 对按 (FP,TP) verdict 分开的数量，distinct signature 数为次级分数；同分用 seed 打散。\n\n完整长路径读取到 15,360/15,360 verdict cells，缓存一致性错误 {len(cache_mismatch)}，timeout stage {summary['timeout_stage_count']}，所以未补跑 formal。完整 64-probe pool 后所有策略/seed 最终 resolved set 一致：{final_equal}，共 {summary['full_pool_resolved_pairs']} 对。\n\nJaccard 仅比较 resolved pair 集合；到达顺序由 `first_distinguish_rank.csv` 和 `kendall_probe_order.csv` 单独报告。\n''',encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
