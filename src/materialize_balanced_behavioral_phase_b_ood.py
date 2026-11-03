from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; V2=ROOT/"outputs/behavioral_preference_pilot_v2"; BASE=V2/"balanced_behavioral_objective_v1/phase_b_refit_all30_v1"; SOURCE=V2/"frozen_top1_ast_v2/query_manifest.json"; AUTH=BASE/"phase_b_ood_authorization_v1.json"; ADAPTER=BASE/"final_adapter_manifest.json"; OUT=BASE/"frozen_ood_top1_v1"
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    target=OUT/"query_manifest.json"
    if target.exists(): raise RuntimeError("refusing to overwrite Phase B OOD manifest")
    auth=json.loads(AUTH.read_text()); source=json.loads(SOURCE.read_text()); adapter=json.loads(ADAPTER.read_text())
    if auth["status"]!="authorized_after_phase_b_smoke_pass_before_any_ood_generation" or sha(SOURCE)!=auth["source_48_query_manifest_sha256"] or len(source["records"])!=48: raise RuntimeError("OOD authorization/source mismatch")
    if adapter["adapter_sha256"]!=auth["phase_b_adapter_sha256"] or sha(ROOT/adapter["adapter_path"]/"adapter_model.safetensors")!=adapter["adapter_sha256"]: raise RuntimeError("Phase B adapter mismatch")
    for row in source["records"]:
        if sha(ROOT/row["prompt_path"])!=row["prompt_sha256"]: raise RuntimeError(f"prompt hash mismatch: {row['case_id']}")
    manifest={"status":"frozen_before_any_phase_b_ood_generation","version":"balanced_behavioral_phase_b_frozen_ood_top1_v1","source_query_manifest_path":str(SOURCE.relative_to(ROOT)).replace("\\","/"),"source_query_manifest_sha256":sha(SOURCE),"query_universe_and_prompts_unchanged":True,"query_count":48,"generation_count":48,"adapter":adapter,"authorization_sha256":sha(AUTH),"decode":{"temperature":0.0,"do_sample":False,"num_return_sequences":1,"max_new_tokens":128,"repair":False,"reranker":False,"selector":False,"heldout_information":False,"constraint":"strict canonical five-key JSON trie then EOS"},"failure_denominator_policy":auth["failure_denominator_policy"],"records":source["records"]}
    OUT.mkdir(parents=True); target.write_text(json.dumps(manifest,indent=2)+"\n"); print(json.dumps({"status":"pass","query_count":48,"generation_count":48,"manifest_sha256":sha(target),"source_query_manifest_sha256":sha(SOURCE),"adapter_sha256":adapter["adapter_sha256"],"authorization_sha256":sha(AUTH)},sort_keys=True))
if __name__=="__main__": main()
