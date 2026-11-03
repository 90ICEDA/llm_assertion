from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1"; TRAIN=BASE/"formal_training_v1/anchor_20_all30"
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    target=BASE/"final_adapter_manifest.json"
    if target.exists(): raise RuntimeError("refusing to overwrite Phase B adapter freeze")
    result=json.loads((TRAIN/"training_result.json").read_text()); checkpoint=(TRAIN/"latest_checkpoint.txt").read_text().strip(); adapter=TRAIN/checkpoint/"adapter_model.safetensors"
    if result["status"]!="pass" or result["completed_steps"]!=4058 or result["loss_token_budget"]!=245760 or checkpoint!="checkpoint-004058": raise RuntimeError("unexpected Phase B training result")
    frozen=json.loads((BASE/"phase_b_refit_all30_v1_frozen.json").read_text())
    if result["schedule_sha256"]!=frozen["schedule_sha256"]: raise RuntimeError("training/frozen schedule mismatch")
    record={"status":"frozen_before_phase_b_ast_smoke","variant":"anchor_20_all30","checkpoint":checkpoint,"adapter_path":str(adapter.parent.relative_to(ROOT)).replace("\\","/"),"adapter_sha256":sha(adapter),"training_result_sha256":sha(TRAIN/"training_result.json"),"phase_b_manifest_sha256":sha(BASE/"phase_b_refit_all30_v1_frozen.json"),"schedule_sha256":result["schedule_sha256"]}
    target.write_text(json.dumps(record,indent=2)+"\n"); (BASE/"final_adapter_hash.sha256").write_text(f"{record['adapter_sha256']}  {str(adapter.relative_to(ROOT)).replace(chr(92),'/')}\n")
    print(json.dumps(record,sort_keys=True))
if __name__=="__main__": main()
