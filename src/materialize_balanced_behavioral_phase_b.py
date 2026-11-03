from __future__ import annotations
import hashlib,json
from pathlib import Path
from tokenizers import Tokenizer
import materialize_balanced_behavioral_token_schedules as scheduler

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1"
SELECTION=BASE/"dev_top1_v1/execution_evaluation_v1/dev_metrics_and_selection.json"; OBJECTIVE=BASE/"balanced_behavioral_objective_v1_frozen.json"
OUT=BASE/"phase_b_refit_all30_v1"; EXPECTED_SELECTION="7eceba54bdc5645b1086e1501298fb9c351f0d48c268e4692f77527ab2387678"
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def rows(p): return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
def main():
    if OUT.exists(): raise RuntimeError("refusing to overwrite frozen Phase B directory")
    if sha(SELECTION)!=EXPECTED_SELECTION: raise RuntimeError("dev selection hash mismatch")
    selection=read(SELECTION); chosen=selection["selection"]
    if chosen["status"]!="selected" or chosen["selected_variant"]!="anchor_20" or chosen["next_action"]!="phase_b_refit_all30": raise RuntimeError("unexpected frozen dev selection")
    objective=read(OBJECTIVE)
    if objective["status"]!="frozen_before_any_balanced_objective_training" or not objective["phase_b_refit"].startswith("after dev selection only, refit"): raise RuntimeError("unexpected frozen objective")
    tokenizer=Tokenizer.from_file(str(ROOT/"outputs/checkpoints/Qwen3-8B/tokenizer.json")); edges=rows(BASE/"dpo_edges_all30.jsonl"); anchors=rows(BASE/"safe_detect_anchors_all30.jsonl")
    scheduler.attach_costs(tokenizer,edges,anchors); schedule,audit=scheduler.schedule_variant(edges,anchors,0.20)
    parents={x["parent_bug_id"] for x in schedule}; edge_parents={x["parent_bug_id"] for x in schedule if x["record_type"]=="dpo_edge"}
    if sum(x["loss_tokens"] for x in schedule)!=245760 or len(parents)!=30 or len(edge_parents)!=30: raise RuntimeError("Phase B all30/budget constraint failed")
    OUT.mkdir(parents=True); schedule_path=OUT/"anchor_20_all30.jsonl"; schedule_path.write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in schedule))
    frozen={"status":"frozen_before_phase_b_training","version":"balanced_behavioral_phase_b_refit_all30_v1","selected_variant":"anchor_20","selection_sha256":sha(SELECTION),"objective_sha256":sha(OBJECTIVE),"dpo_edge_pool_sha256":sha(BASE/"dpo_edges_all30.jsonl"),"anchor_pool_sha256":sha(BASE/"safe_detect_anchors_all30.jsonl"),"schedule_sha256":sha(schedule_path),"total_loss_token_budget":245760,"effective_parent_count":len(parents),"effective_dpo_parent_count":len(edge_parents),"anchor_fraction":0.20,"schedule_audit":audit,"forbidden_before_smoke_pass":["new frozen 48-query OOD generation","OOD outcome access","case-specific OOD tuning"]}
    frozen_path=OUT/"phase_b_refit_all30_v1_frozen.json"; frozen_path.write_text(json.dumps(frozen,indent=2)+"\n")
    hashes={p.name:sha(p) for p in sorted(OUT.iterdir())}; (OUT/"SHA256SUMS.json").write_text(json.dumps(hashes,indent=2)+"\n")
    print(json.dumps({"status":"materialized_and_frozen","schedule_sha256":sha(schedule_path),"frozen_manifest_sha256":sha(frozen_path),"steps":len(schedule),"loss_token_budget":245760,"effective_parent_count":len(parents),"effective_dpo_parent_count":len(edge_parents),"bucket_tokens":audit["bucket_tokens"],"anchor_repetitions":audit["anchor_repetitions"],"max_anchor_example_token_share":audit["max_anchor_example_token_share"],"max_dpo_candidate_degree_in_any_cycle":audit["max_dpo_candidate_degree_in_any_cycle"]},sort_keys=True))
if __name__=="__main__": main()
