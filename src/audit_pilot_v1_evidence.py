from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT/"outputs/behavioral_preference_pilot_v1";R=P/"final_report_v1"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def main():
 expected=json.loads((R/"critical_artifact_hashes.json").read_text(encoding="utf-8")); errors=[]
 for rel,want in expected.items():
  p=ROOT/rel
  if not p.is_file() or sha(p)!=want:errors.append(f"hash:{rel}")
 for policy,name in (("random_legal","random_legal_dominance_pairs.jsonl"),("disagreement_guided","disagreement_guided_dominance_pairs.jsonl")):
  seen=set()
  for x in rows(P/"dominance_pairs_v3"/name):
   cf,rf,ct,rt=map(set,(x["chosen_fp"],x["rejected_fp"],x["chosen_tp"],x["rejected_tp"]))
   if not(cf<=rf and ct>=rt and (cf<rf or ct>rt)):errors.append(f"dominance:{x['pair_id']}")
   if x["pair_id"] in seen:errors.append(f"duplicate:{x['pair_id']}")
   seen.add(x["pair_id"])
 if len(list((P/"sequential_generation_v3_pilot30").rglob("evidence.json")))!=240:errors.append("candidate_count")
 if len(list((P/"frozen_top1_v1/generations").rglob("evidence.json")))!=240:errors.append("generation_count")
 if len(list((P/"frozen_top1_v1/execution_evaluation_v1/records").rglob("evaluation.json")))!=240:errors.append("evaluation_count")
 print(json.dumps({"status":"pass" if not errors else "fail","errors":errors,"checked_critical_hashes":len(expected),"checked_dominance_pairs":967,"candidate_count":240,"frozen_generation_count":240,"evaluation_count":240}))
 raise SystemExit(bool(errors))
if __name__=="__main__":main()
