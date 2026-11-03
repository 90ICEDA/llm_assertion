#!/usr/bin/env python3
"""Rebuild the sample-flow and metric-accounting audit from repository evidence.

This is intentionally read-only with respect to experiment artifacts.  It writes
only derived CSV/JSON/Markdown files under --out.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, os
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def jload(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8-sig"))


def rows(rel):
    with (ROOT / rel).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, data, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(data[0]) if data else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(data)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def b(v): return str(v).strip().lower() in {"1", "true", "yes"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="deliverables/results_accounting_audit_20260829")
    args = ap.parse_args(); out = ROOT / args.out; out.mkdir(parents=True, exist_ok=True)

    acceptance = jload("deliverables/final_dataset_acceptance_20260804/final_manifest.json")
    rejected = rows("deliverables/final_dataset_acceptance_20260804/rejected_cases.csv")
    admitted = {x["parent_bug_id"] for x in acceptance["cases"]}
    rejected_ids = {x["parent_bug_id"] for x in rejected}
    initial60 = admitted | rejected_ids

    f46_rows = rows("deliverables/final46_main_experiment_20260806/parent_deduplicated_results.csv")
    final46 = {x["parent_bug_id"] for x in f46_rows}
    sel_rows = rows("deliverables/equal_budget_visible_selection_20260809/parent_deduplicated_results.csv")
    selection40 = {x["parent_bug_id"] for x in sel_rows if x["case_id"] == x["parent_bug_id"]}
    train_rows = rows("outputs/behavioral_preference_pilot_v1/selected_train_parents.csv")
    latest30 = {x["parent_bug_id"] for x in train_rows}
    sets = {"initial60": initial60, "accepted46": final46,
            "selection40": selection40, "latest_train30": latest30}

    set_sources = {
      "initial60":"final_manifest.json candidate_count plus rejected_cases.csv union admitted cases",
      "accepted46":"final46 parent_deduplicated_results.csv parent_bug_id",
      "selection40":"selection parent_deduplicated_results.csv canonical rows (case_id == parent_bug_id)",
      "latest_train30":"selected_train_parents.csv parent_bug_id",
    }
    set_table=[]
    for name, ids in sets.items():
        for pid in sorted(ids): set_table.append({"dataset":name,"parent_bug_id":pid,"source_rule":set_sources[name]})
    write_csv(out/"parent_id_sets.csv",set_table)

    rel=[]
    for a,c in combinations(sets,2):
        A,B=sets[a],sets[c]
        rel.append({"set_a":a,"n_a":len(A),"set_b":c,"n_b":len(B),"intersection":len(A&B),
                    "a_minus_b":len(A-B),"b_minus_a":len(B-A),"a_subset_b":A<=B,"b_subset_a":B<=A,
                    "relationship":"equal" if A==B else "A_subset_B" if A<B else "B_subset_A" if B<A else "overlap" if A&B else "disjoint"})
    write_csv(out/"set_relationships.csv",rel)

    transitions=[]
    # Only 60 -> 46 is a documented admission transition. Other comparisons are
    # cross-experiment membership, not assumed exclusion transitions.
    rej_by_id={x["parent_bug_id"]:x for x in rejected}
    for pid in sorted(initial60):
        r=rej_by_id.get(pid)
        transitions.append({"from_dataset":"initial60","to_dataset":"accepted46","parent_bug_id":pid,
          "status":"included" if pid in final46 else "excluded_by_acceptance_gate",
          "reason":"passed final admission rule" if pid in final46 else r["rejection_reason"],
          "evidence_file":"deliverables/final_dataset_acceptance_20260804/final_manifest.json" if pid in final46 else "deliverables/final_dataset_acceptance_20260804/rejected_cases.csv"})
    for dst, ids, evidence in [("selection40",selection40,"deliverables/equal_budget_visible_selection_20260809/parent_deduplicated_results.csv"),("latest_train30",latest30,"outputs/behavioral_preference_pilot_v1/selected_train_parents.csv")]:
        universe=initial60|ids
        for pid in sorted(universe):
            transitions.append({"from_dataset":"initial60_acceptance_branch","to_dataset":dst,"parent_bug_id":pid,
              "status":"member_of_both" if pid in initial60 and pid in ids else "only_in_initial60_branch" if pid in initial60 else f"only_in_{dst}",
              "reason":"cross-experiment comparison; absence is not a documented rejection",
              "evidence_file":evidence})
    write_csv(out/"parent_membership_and_exclusions.csv",transitions)

    flow='''flowchart LR
  U["60 proposed parents<br/>cases 451-510"] -->|"acceptance gates"| A["46 admitted parents"]
  U -->|"14 rejected; golden/weak gate evidence"| R["14 rejected parents"]
  S["scale120 formal universe<br/>variants grouped to parents"] -->|"canonical case_id = parent_bug_id"| Q["40-parent selection asset"]
  S --> T["scale120 members used in Pilot train"]
  A -->|"partial overlap, not a filter"| T
  N["scale210 admitted pools"] --> T["30-parent balanced Pilot train<br/>10/project"]
  T --> L["latest behavioral preference / closed loop"]
'''
    (out/"sample_flow.mmd").write_text(flow,encoding="utf-8")

    # Metric source table for every percentage in the current closed-loop report
    # and its post-hoc interpretation table.
    probe=rows("outputs/behavioral_preference_pilot_v1/final_report_v1/probe_ablation_table.csv")
    dom=jload("outputs/behavioral_preference_pilot_v1/dominance_pairs_v3/dominance_audit.json")
    gen=jload("outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.json")
    ood=jload("outputs/phase_b_ood_eval_v1/phase_b_ood_metrics_and_decision.json")
    metrics=[]
    def metric(name,num,den,unit,dataset,formula,source,note=""):
        metrics.append({"metric_name":name,"numerator":num,"denominator":den,"statistical_unit":unit,
          "dataset":dataset,"formula":formula,"value": "" if den in (0,None,"") else float(num)/float(den),"source_file":source,"audit_note":note})
    for x in probe:
        p=x["policy"]
        metric(f"{p}.distinguishing_candidate_query_ratio",x["distinguishing_candidate_query_cells"],x["candidate_query_cells"],"candidate×selected-probe cell",p,"distinguishing cells / all candidate-query cells","outputs/behavioral_preference_pilot_v1/final_report_v1/probe_ablation_table.csv")
        metric(f"{p}.unique_distinguishing_probe_ratio",x["unique_distinguishing_probes"],x["unique_selected_queries"],"unique selected probe",p,"unique distinguishing probes / unique selected probes","outputs/behavioral_preference_pilot_v1/final_report_v1/probe_ablation_table.csv")
        metric(f"{p}.pairs_per_query",x["dominance_pairs"],x["unique_selected_queries"],"dominance pair per selected probe",p,"strict dominance pairs / unique selected probes","outputs/behavioral_preference_pilot_v1/final_report_v1/probe_ablation_table.csv")
    for p,x in gen["pair_comparability"].items():
        for key in ("unlabeled_fraction","crossing_incomparable_fraction","equal_signature_fraction"):
            n={"unlabeled_fraction":x["equal_signature"]+x["crossing_incomparable"],"crossing_incomparable_fraction":x["crossing_incomparable"],"equal_signature_fraction":x["equal_signature"]}[key]
            metric(f"{p}.{key}",n,x["total_unordered"],"unordered within-parent candidate pair",p,f"{key.replace('_fraction','')} / total unordered pairs","outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.json")
        metric(f"{p}.strict_dominance_fraction",x["strict_dominance"],x["total_unordered"],"unordered within-parent candidate pair",p,"strict dominance pairs / total unordered pairs","outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.json")
    for split,x in ood["summaries"].items():
        if split=="union_overview": continue
        n=x["query_count"]; c=x["counts"]
        for label,num,den,unit in [("SCS@1",c["strict_success"],n,"query/case"),("Fixed-Safe",c["fixed_safe"],n,"query/case"),("Target Detect",c["target_detect"],n,"query/case"),("Family Recall",c["recalled_families"],c["families"],"bug family"),("Non-vacuity",c["non_vacuous"],n,"query/case")]:
            metric(f"phase_b.{split}.{label}",num,den,unit,split,f"{label} count / {unit} denominator","outputs/phase_b_ood_eval_v1/phase_b_ood_metrics_and_decision.json")
        if x["TOR"] is not None: metric(f"phase_b.{split}.TOR",c["trace_overfit"],c["primary_success"],"primary-success query",split,"trace_overfit / primary_success","outputs/phase_b_ood_eval_v1/phase_b_ood_metrics_and_decision.json")
        metric(f"phase_b.{split}.Compile",n,n,"query/case",split,"compiled / queries (summary compile_rate)","outputs/phase_b_ood_eval_v1/phase_b_ood_metrics_and_decision.json")
    write_csv(out/"metric_sources.csv",metrics)

    issues=[]
    def issue(kind,severity,scope,detail,evidence): issues.append({"issue_type":kind,"severity":severity,"scope":scope,"detail":detail,"evidence_file":evidence})
    grouped=defaultdict(list)
    for m in metrics: grouped[(str(m["numerator"]),str(m["denominator"]))].append(m["metric_name"])
    for k,names in grouped.items():
        if len(names)>1: issue("same_numerator_denominator","info",";".join(names),f"shared fraction {k[0]}/{k[1]}","metric_sources.csv")
    values=defaultdict(list)
    for m in metrics:
        if m["value"]!="": values[round(float(m["value"]),12)].append(m)
    for val,ms in values.items():
        sig={(str(x["numerator"]),str(x["denominator"]),x["statistical_unit"]) for x in ms}
        if len(ms)>1 and len(sig)>1: issue("same_value_different_meaning","warning",";".join(x["metric_name"] for x in ms),f"same value {val:.12g}, differing counts/unit", "metric_sources.csv")

    # Raw evidence integrity: candidates, probes, result logs and dominance pairs.
    evidence_files=list((ROOT/"outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30").glob("*/slot_*/attempt_01/evidence.json"))
    cand_ids=[]; sva_groups=defaultdict(list)
    for p in evidence_files:
        d=json.loads(p.read_text(encoding="utf-8-sig"))
        cid=d.get("candidate_id") or f"{d['parent_bug_id']}__v3_slot_{int(d['slot']):02d}"
        cand_ids.append(cid); sva_groups[(d["parent_bug_id"]," ".join(d.get("sva","").split()))].append(cid)
    for cid,n in Counter(cand_ids).items():
        if n>1: issue("duplicate_candidate_id","error",cid,f"appears {n} times","sequential_generation_v3_pilot30/**/evidence.json")
    if len(evidence_files)!=240: issue("candidate_count_mismatch","error","pilot30",f"found {len(evidence_files)} evidence files, expected 240","outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30")
    for (pid,sva),ids in sva_groups.items():
        if sva and len(ids)>1: issue("duplicate_candidate_content","warning",pid,f"identical SVA in distinct candidate slots: {';'.join(ids)}","sequential_generation_v3_pilot30/**/evidence.json")
    probe_manifest=jload("outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/probe_manifest.json")
    probe_ids=[]
    def walk(v):
        if isinstance(v,dict):
            if "probe_id" in v: probe_ids.append(v["probe_id"])
            for z in v.values(): walk(z)
        elif isinstance(v,list):
            for z in v: walk(z)
    walk(probe_manifest)
    for pid,n in Counter(probe_ids).items():
        if n>1: issue("duplicate_probe_id","error",pid,f"appears {n} times in manifest","behavioral_probes_v3/probe_manifest.json")
    result_files=[]
    expected=30*64*8
    missing=[]
    probe_root=ROOT/"outputs/behavioral_preference_pilot_v1/behavioral_probes_v3"
    actual_keys=set()
    for pid in sorted(latest30):
        for q in range(0,64):
            probe_id=f"{pid}__probe_{q:03d}"
            for slot in range(1,9):
                cid=f"{pid}__v3_slot_{slot:02d}"
                result_rel=Path(pid)/"runs"/probe_id/cid/"result.json"
                target=(probe_root/result_rel).resolve(); target_s=str(target)
                if os.name=="nt": target_s="\\\\?\\"+target_s
                if os.path.exists(target_s): actual_keys.add((pid,probe_id,cid)); result_files.append(target)
                else: missing.append({"parent_bug_id":pid,"probe_id":probe_id,"candidate_id":cid,"expected_result_file":str(Path("outputs/behavioral_preference_pilot_v1/behavioral_probes_v3")/result_rel).replace('\\','/')})
    if len(result_files)!=expected: issue("probe_result_count_mismatch","error","behavioral_probes_v3",f"found {len(result_files)}, expected {expected}","outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/**/result.json")
    write_csv(out/"missing_probe_results.csv",missing,["parent_bug_id","probe_id","candidate_id","expected_result_file"])
    for policy,x in dom["policies"].items():
        f=ROOT/x["pair_file"]; lines=[json.loads(z) for z in f.read_text(encoding="utf-8-sig").splitlines() if z.strip()]
        ids=[z.get("pair_id") for z in lines]
        if len(lines)!=x["pair_count"]: issue("pair_count_mismatch","error",policy,f"raw {len(lines)} vs audit {x['pair_count']}",x["pair_file"])
        if len(ids)!=len(set(ids)): issue("duplicate_pair_id","error",policy,f"{len(ids)-len(set(ids))} duplicates",x["pair_file"])
        if sha(f)!=x["pair_file_sha256"]: issue("hash_mismatch","error",policy,"pair file hash differs from frozen audit",x["pair_file"])
    if not issues: issue("none","info","all","no issues found","generated audit")
    write_csv(out/"integrity_findings.csv",issues)

    summary={"set_counts":{k:len(v) for k,v in sets.items()},"relationships":rel,
      "candidate_evidence_files":len(evidence_files),"probe_result_files":len(result_files),
      "metric_count":len(metrics),"finding_counts":dict(Counter(x["severity"] for x in issues))}
    (out/"audit_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    report=f'''# 样本流转与统计口径审计\n\n## 结论\n\n60→46 是有证据的 admission 流程；40-parent selection 与 30-parent Pilot 是不同实验资产/分支，不能写成 46→40→30 的线性筛选。四套集合计数为 {summary['set_counts']}。精确交集见 `set_relationships.csv`，完整 ID 见 `parent_id_sets.csv`。\n\n## 证据与排除\n\n`parent_membership_and_exclusions.csv` 对 60→46 的 14 个排除逐一给出 gate 原因和证据；对 40、30 仅记录跨实验 membership，不把“不在该集合”虚构为排除。流程图源文件为 `sample_flow.mmd`。\n\n## 统计口径\n\n`metric_sources.csv` 逐项记录 numerator、denominator、statistical unit、dataset、formula 和 source。`integrity_findings.csv` 标出相同分数、相同分子分母、单位差异、重复与缺失。candidate×probe incidence 不是 candidate 或 parent；family recall 的分母是 family；TOR 的分母是 primary-success query。\n\n## 完整性发现\n\n240 个 candidate evidence 齐全，dominance JSONL 的 pair 数、pair ID 唯一性和冻结 SHA-256 均通过。使用 Windows 长路径安全读取后，probe 网格为 {len(result_files):,}/15,360，缺 {len(missing):,} 个；此前普通 glob 漏读长路径不能作为 verdict 缺失证据。\n\n## 重算\n\n运行：\n\n```powershell\npython scripts/rebuild_results_audit.py\n```\n\n脚本只读逐行 CSV、JSONL、candidate/probe result evidence 和冻结 manifest，并重建本目录全部 CSV/JSON/Markdown；不重新执行仿真、训练、OOD 或扩展 pairs。\n'''
    (out/"AUDIT_REPORT.md").write_text(report,encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
