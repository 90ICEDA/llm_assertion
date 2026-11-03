import hashlib,json
from pathlib import Path
import train_balanced_behavioral_dev_qwen3 as implementation

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1"
implementation.SCHEDULES=BASE/"phase_b_refit_all30_v1"
implementation.OUT=BASE/"phase_b_refit_all30_v1/formal_training_v1"
implementation.VARIANTS=("anchor_20_all30",)
if __name__=="__main__":
    phase=BASE/"phase_b_refit_all30_v1"; manifest=json.loads((phase/"phase_b_refit_all30_v1_frozen.json").read_text())
    schedule=phase/"anchor_20_all30.jsonl"
    if manifest["status"]!="frozen_before_phase_b_training" or manifest["selected_variant"]!="anchor_20": raise RuntimeError("unexpected Phase B freeze")
    if hashlib.sha256(schedule.read_bytes()).hexdigest()!=manifest["schedule_sha256"] or manifest["effective_parent_count"]!=30 or manifest["total_loss_token_budget"]!=245760: raise RuntimeError("Phase B schedule/freeze mismatch")
    implementation.main()
