from __future__ import annotations

import csv, hashlib, json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "outputs/behavioral_preference_pilot_v1"
R = P / "final_report_v1"

def load(path): return json.loads(path.read_text(encoding="utf-8-sig"))
def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def jsonl(path): return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def selected_run_cost(parent, probe_id, candidate_id):
    path=P/"behavioral_probes_v3"/parent/"runs"/probe_id/candidate_id/"result.json"
    if not path.is_file(): return None
    d=load(path); seconds=0.0; timeouts=0
    for rtl in ("correct","buggy"):
        for stage in ("compile","simulation"):
            x=d["rtl"][rtl][stage]; seconds += float(x.get("wall_clock_seconds",0)); timeouts += int(x.get("timeout",False))
    return seconds,timeouts

def main():
    with (P/"selected_train_parents.csv").open(encoding="utf-8-sig",newline="") as f: parents=list(csv.DictReader(f))
    gen=list((P/"sequential_generation_v3_pilot30").rglob("evidence.json"))
    ev=[load(x) for x in gen]
    failure_counts=Counter()
    for x in ev:
        if not x.get("icarus_compile_ok"): failure_counts["compile_failure"]+=1
        if not x.get("signal_legal"): failure_counts["signal_illegal"]+=1
        if not x.get("fixed_safe"): failure_counts["fixed_false_positive"]+=1
        if not x.get("target_detect"): failure_counts["target_miss"]+=1
        if not x.get("antecedent_hit") or not x.get("non_vacuous"): failure_counts["vacuous"]+=1
    probe=load(P/"behavioral_probes_v3/probe_manifest.json")
    dom=load(P/"dominance_pairs_v3/dominance_audit.json")
    policy_rows={p:[x for x in probe["candidate_policy_records"] if x["probe_policy"]==p] for p in probe["policies"]}
    ablation=[]
    for policy,rows in policy_rows.items():
        cells=sum(x["query_budget"] for x in rows)
        dist_cells=sum(len(x["distinguishing_probe_ids"]) for x in rows)
        unique_dist=defaultdict(set); signatures=set(); seconds=0.0; timeouts=0; observed_cost_cells=0; missing_cost_cells=0
        for x in rows:
            unique_dist[x["parent_bug_id"]].update(x["distinguishing_probe_ids"])
            signatures.add((x["parent_bug_id"],tuple(x["fp_probe_ids"]),tuple(x["tp_mutant_ids"])))
            for pid in x["selected_probe_ids"]:
                cost=selected_run_cost(x["parent_bug_id"],pid,x["candidate_id"])
                if cost is None: missing_cost_cells+=1
                else:
                    s,t=cost; seconds+=s; timeouts+=t; observed_cost_cells+=1
        pair_count=dom["policies"][policy]["pair_count"]
        ablation.append({"policy":policy,"parents":30,"candidates":240,"queries_per_parent":32,
            "unique_selected_queries":960,"candidate_query_cells":cells,
            "distinguishing_candidate_query_cells":dist_cells,
            "distinguishing_candidate_query_ratio":dist_cells/cells,
            "unique_distinguishing_probes":sum(map(len,unique_dist.values())),
            "unique_distinguishing_probe_ratio":sum(map(len,unique_dist.values()))/960,
            "unique_candidate_fp_tp_signatures":len(signatures),"dominance_pairs":pair_count,
            "pairs_per_query":pair_count/960,"observed_selected_query_execution_wall_clock_seconds":seconds,
            "wall_clock_observed_cells":observed_cost_cells,"wall_clock_missing_cells":missing_cost_cells,
            "timeout_stage_count_on_observed_cells":timeouts})
    joint_wall=sum(float(x["wall_clock_seconds"]) for x in probe["parent_results"])
    metrics=load(P/"frozen_top1_v1/execution_evaluation_v1/frozen_top1_metrics.json")
    extraction={}
    for method_dir in (P/"frozen_top1_v1/generations").iterdir():
        docs=[load(x) for x in method_dir.rglob("evidence.json")]
        extraction[method_dir.name]={"count":len(docs),"extracted":sum(bool(x["sva_extracted"]) for x in docs),
            "extraction_rate":sum(bool(x["sva_extracted"]) for x in docs)/len(docs),"maxed_512":sum(x["output_tokens"]==512 for x in docs)}
    adapter_lines=(P/"formal_training_v2/final_adapter_hashes.sha256").read_text(encoding="utf-8").splitlines()
    adapters={line.split()[-1].split("/")[-3]:{"sha256":line.split()[0],"checkpoint":line.split()[-1]} for line in adapter_lines if line.strip()}
    corpus=load(P/"training_corpora_v2/formal_training_v2_frozen.json")
    report={"status":"complete_no_go","data":{"parents":len(parents),"projects":dict(Counter(x["source_project"] for x in parents)),
      "bug_classes":dict(Counter(x["bug_class"] for x in parents)),"candidate_count":len(ev),"observed_failure_modes":dict(failure_counts)},
      "probe_ablation":{"operational_definitions":{"distinguishing_candidate_query_ratio":"sum candidate-specific distinguishing_probe_ids / (240*32)",
      "unique_failure_modes":"unique per-parent candidate (FP set, TP set) signatures","wall_clock":"sum of raw compile/simulation durations for selected candidate-query cells; selector overhead excluded",
      "joint_end_to_end_wall_clock_seconds":"sum parent_result wall clocks; both policies combined and not attributable separately"},"rows":ablation,
      "joint_end_to_end_wall_clock_seconds":joint_wall},"dominance":dom,"training":{"frozen_config":corpus,"adapters":adapters},
      "frozen_top1":{"extraction":extraction,"metrics":metrics},"project_ood":"N/A: training covers all three frozen projects",
      "decision":load(P/"frozen_top1_v1/execution_evaluation_v1/pilot_go_no_go_v1.json")}
    dump(R/"pilot_v1_final_report.json",report)
    with (R/"probe_ablation_table.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(ablation[0]));w.writeheader();w.writerows(ablation)
    lines=["# Behavioral Preference Pilot v1 — Final Report","","Status: **NO-GO**. Do not expand to 3,000–10,000 pairs.","",
      "## Data",f"- {len(parents)} parents, {len(set(x['source_project'] for x in parents))} projects, {len(ev)} executable candidates.",
      f"- Observed failure modes: `{json.dumps(dict(failure_counts),ensure_ascii=False)}`.","","## Probe ablation","",
      "| Policy | Distinguishing cells | Unique distinguishing probes | Pairs/query | Unique FP/TP signatures | Timeouts | Selected execution seconds | Frozen SCS@1 |",
      "|---|---:|---:|---:|---:|---:|---:|---:|"]
    union=metrics["summaries"]["union_overview"]["methods"]
    for x in ablation:
        method="random_probe_dominance_dpo" if x["policy"]=="random_legal" else "full_disagreement_dominance_dpo"
        lines.append(f"| {x['policy']} | {x['distinguishing_candidate_query_ratio']:.2%} | {x['unique_distinguishing_probe_ratio']:.2%} | {x['pairs_per_query']:.4f} | {x['unique_candidate_fp_tp_signatures']} | {x['timeout_stage_count_on_observed_cells']} | {x['observed_selected_query_execution_wall_clock_seconds']:.2f} ({x['wall_clock_observed_cells']}/{x['candidate_query_cells']} cells) | {union[method]['SCS@1']:.2%} |")
    lines += ["",f"Joint end-to-end probe wall-clock (both policies, inseparable in v1): {joint_wall:.2f}s.","",
      "## Dominance",f"- random legal: {dom['policies']['random_legal']['pair_count']} strict pairs.",
      f"- disagreement guided: {dom['policies']['disagreement_guided']['pair_count']} strict pairs.","- No cross-parent/policy comparisons; incomparable relations omitted.","",
      "## Frozen Top-1","- All five adapters used the same 48 queries, greedy one-shot generation, no repair/reranking/selector.",
      "- Project-OOD: structural N/A because Pilot training covers all three frozen projects.","- Full method SCS@1 is 0% on unseen-parent and unseen-bug-family.","",
      "## Decision","The +5pp SCS@1 gate failed and Fixed-Safe decreased. Pilot v1 is NO-GO."]
    (R/"pilot_v1_final_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    critical=[P/"behavioral_probes_v3/probe_manifest.json",P/"dominance_pairs_v3/dominance_audit.json",
      P/"training_corpora_v2/formal_training_v2_frozen.json",P/"formal_training_v2/final_adapter_hashes.sha256",
      P/"frozen_top1_v1/query_manifest.json",P/"frozen_top1_v1/execution_evaluation_v1/frozen_top1_metrics.json",
      P/"frozen_top1_v1/execution_evaluation_v1/pilot_go_no_go_v1.json",R/"pilot_v1_final_report.json",R/"probe_ablation_table.csv"]
    dump(R/"critical_artifact_hashes.json",{str(x.relative_to(ROOT)).replace('\\','/'):sha(x) for x in critical})
    print(json.dumps({"status":"pass","report":str(R),"ablation":ablation},ensure_ascii=False))
if __name__=="__main__": main()
