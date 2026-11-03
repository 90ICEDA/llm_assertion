from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; FINAL=ROOT/"outputs/behavioral_preference_closed_loop_final_v1"
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 errors=[]; manifest=json.loads((FINAL/"phase_b_final_manifest.json").read_text()); expected=json.loads((FINAL/"SHA256SUMS.json").read_text())
 for name,digest in expected.items():
  p=FINAL/name
  if not p.is_file() or sha(p)!=digest: errors.append(f"final hash mismatch: {name}")
 artifacts=json.loads((FINAL/"evaluation_artifact_hashes.json").read_text())
 for rel,digest in artifacts.items():
  p=ROOT/rel
  if not p.is_file() or sha(p)!=digest: errors.append(f"artifact hash mismatch: {rel}")
 for item in manifest["frozen_scope_assets"].values():
  if sha(ROOT/item["path"])!=item["sha256"]: errors.append(f"frozen scope hash mismatch: {item['path']}")
 if manifest["counts"]!={"train_parents":30,"projects":3,"candidates":240,"random_dominance_pairs":483,"guided_dominance_pairs":484,"phase_b_smoke":24,"frozen_ood_queries":48,"frozen_ood_evaluations":48}: errors.append("count contract mismatch")
 if manifest["deletion_audit"]["status"]!="pass" or manifest["leakage_audit"]["status"]!="pass": errors.append("deletion/leakage audit failed")
 if manifest["decision"]!="NO-GO" or manifest["expansion_authorized"] is not False: errors.append("decision contract mismatch")
 print(json.dumps({"status":"pass" if not errors else "fail","errors":errors,"checked_final_hashes":len(expected),"checked_evaluation_artifacts":len(artifacts),"candidate_count":240,"dominance_pairs":967,"smoke_count":24,"frozen_generation_count":48,"evaluation_count":48,"decision":manifest["decision"]},sort_keys=True))
 if errors: raise SystemExit(1)
if __name__=="__main__": main()
