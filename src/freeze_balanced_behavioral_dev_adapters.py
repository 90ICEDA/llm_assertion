from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1"
TRAIN=BASE/"formal_training_dev_v1"; VARIANTS=("anchor_10","anchor_20","anchor_25")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    target=TRAIN/"final_adapter_manifest.json"
    if target.exists(): raise RuntimeError("refusing to overwrite frozen dev adapter manifest")
    methods={}; hash_lines=[]
    for variant in VARIANTS:
        directory=TRAIN/variant; result=json.loads((directory/"training_result.json").read_text())
        if result["status"]!="pass" or result["completed_steps"]!=result["steps"] or result["loss_token_budget"]!=245760:
            raise RuntimeError(f"incomplete training: {variant}")
        checkpoint=(directory/"latest_checkpoint.txt").read_text().strip(); adapter=directory/checkpoint/"adapter_model.safetensors"; digest=sha(adapter)
        relative=str(adapter.relative_to(ROOT)).replace("\\","/"); hash_lines.append(f"{digest}  {relative}\n")
        methods[variant]={"checkpoint":checkpoint,"adapter_path":str(adapter.parent.relative_to(ROOT)).replace("\\","/"),"adapter_sha256":digest,"training_result_sha256":sha(directory/"training_result.json"),"schedule_sha256":result["schedule_sha256"]}
    hashes=TRAIN/"final_adapter_hashes.sha256"; hashes.write_text("".join(hash_lines))
    manifest={"status":"frozen_before_train_parent_dev_generation","frozen_objective_sha256":sha(BASE/"balanced_behavioral_objective_v1_frozen.json"),"variant_count":3,"methods":methods,"hash_file_sha256":sha(hashes)}
    target.write_text(json.dumps(manifest,indent=2)+"\n"); print(json.dumps(manifest,sort_keys=True))
if __name__=="__main__": main()
