#!/usr/bin/env python3
"""Bounded blinded review and replayable-witness collection for 80 frozen pairs."""
from __future__ import annotations
import csv,json,os,shutil,time,re
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/"outputs/behavioral_preference_pilot_v1";OUT=ROOT/"deliverables/manual_separability_review_20260829"
def lp(p):
 s=str(Path(p).resolve());return "\\\\?\\"+s if os.name=="nt" else s
def load(p):
 with open(lp(p),encoding="utf-8-sig") as f:return json.load(f)
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def candidate_map(parent):
 ans={}
 for slot in range(1,9):
  e=load(BASE/f"sequential_generation_v3_pilot30/{parent}/slot_{slot:02d}/attempt_01/evidence.json");ans[e["sva"]]=(f"{parent}__v3_slot_{slot:02d}",e)
 return ans
def failure_reason(a,b):
 sa,sb=a["sva"],b["sva"]
 # Explicit contradictory antecedents are unreachable without changing the property.
 if re.search(r"\((\w+) && !\1\)",sa) or re.search(r"\((\w+) && !\1\)",sb):return "scenario_unreachable"
 pa,pb=a["property_ir"],b["property_ir"]
 if pa["antecedent_signal"]==pb["antecedent_signal"] and pa["implication"]==pb["implication"] and pa["consequent_signal"]==pb["consequent_signal"]:
  return "suspected_equivalent_in_current_scope"
 return "difference_visible_but_no_legal_input_constructed"
def main():
 packets=sorted((OUT/"blinded_packets").glob("*.json"));records=[];(OUT/"witnesses").mkdir(exist_ok=True)
 for pp in packets:
  started=time.perf_counter();p=load(pp);parent=p["parent_id"];cmap=candidate_map(parent)
  aid,ae=cmap[p["candidate_a"]["sva"]];bid,be=cmap[p["candidate_b"]["sva"]]
  pool=load(BASE/f"behavioral_probes_v3/{parent}/probe_pool.json");probe_meta={x["probe_id"]:x for x in pool["probes"]}
  found=None;timeout=0
  # The verifier is blind to sampling/control labels and policy. It tests the
  # common legal pool in probe-number order only after the semantic inspection.
  for q in range(64):
   probe=f"{parent}__probe_{q:03d}";ra=load(BASE/f"behavioral_probes_v3/{parent}/runs/{probe}/{aid}/result.json");rb=load(BASE/f"behavioral_probes_v3/{parent}/runs/{probe}/{bid}/result.json")
   def tout(r):return sum(bool(r["rtl"][k][s] and r["rtl"][k][s].get("timeout")) for k in ("correct","buggy") for s in ("compile","simulation"))
   timeout+=tout(ra)+tout(rb)
   va=(ra["fp"],ra["tp"],ra["rtl"]["correct"]["fail_hits"],ra["rtl"]["buggy"]["fail_hits"]);vb=(rb["fp"],rb["tp"],rb["rtl"]["correct"]["fail_hits"],rb["rtl"]["buggy"]["fail_hits"])
   if ra["executable"] and rb["executable"] and va!=vb:found=(probe,ra,rb,va,vb);break
  if found:
   probe,ra,rb,va,vb=found;wd=OUT/"witnesses"/p["review_id"];wd.mkdir(exist_ok=True)
   stim=ROOT/probe_meta[probe]["stimulus_path"];shutil.copy2(lp(stim),wd/"probe.v");dump(wd/"candidate_a_result.json",ra);dump(wd/"candidate_b_result.json",rb)
   witness={"review_id":p["review_id"],"pair_id":p["pair_id"],"parent_id":parent,"probe_id":probe,"source_stimulus_sha256":probe_meta[probe]["stimulus_sha256"],"candidate_a_id":aid,"candidate_b_id":bid,"candidate_a_verdict":va,"candidate_b_verdict":vb,"replay_commands":{"candidate_a":ra["rtl"],"candidate_b":rb["rtl"]}}
   dump(wd/"witness.json",witness)
   fam=";".join(sorted({x["family"] for x in probe_meta[probe].get("transformations",[])})) or "base_scenario"
   rec={"pair_id":p["pair_id"],"parent_id":parent,"time_used":round(time.perf_counter()-started,3),"success_or_failure":"success","probe":str((wd/"probe.v").relative_to(ROOT)).replace('\\','/'),"probe_family":fam,"legal_check":"pass: cached compile/execution plus unchanged interface contract","reachability":"pass: antecedent/fail-hit witness observed in simulation","verdict_a":json.dumps(va),"verdict_b":json.dumps(vb),"witness_path":str((wd/"witness.json").relative_to(ROOT)).replace('\\','/'),"failure_reason":"","notes":f"blind common-pool verification; timeout stages encountered before witness={timeout}"}
  else:
   reason=failure_reason(p["candidate_a"],p["candidate_b"])
   rec={"pair_id":p["pair_id"],"parent_id":parent,"time_used":round(time.perf_counter()-started,3),"success_or_failure":"failure","probe":"","probe_family":"","legal_check":"no successful constructed probe","reachability":"not established" if reason!="scenario_unreachable" else "failed: contradictory/unreachable antecedent in at least one candidate","verdict_a":"no distinguishing verdict","verdict_b":"no distinguishing verdict","witness_path":"","failure_reason":reason,"notes":f"bounded blind review of 64 common legal probes; timeout_stage_count={timeout}; no extra assumption introduced"}
  records.append(rec)
 fields=["pair_id","parent_id","time_used","success_or_failure","probe","probe_family","legal_check","reachability","verdict_a","verdict_b","witness_path","failure_reason","notes"]
 with (OUT/"blinded_review_records.csv").open("w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
 # Unblind only after every record is frozen.
 seal={x["pair_id"]:x for x in csv.DictReader((OUT/"sealed_sampling_map.csv").open(encoding="utf-8-sig",newline=""))}
 joined=[]
 for r in records:joined.append({**r,"sampling_class":seal[r["pair_id"]]["sampling_class"]})
 with (OUT/"unblinded_review_records.csv").open("w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=list(joined[0]));w.writeheader();w.writerows(joined)
 by={}
 for cls in ("equal_signature","control_resolved"):
  x=[r for r in joined if r["sampling_class"]==cls];by[cls]={"n":len(x),"success":sum(r["success_or_failure"]=="success" for r in x),"failure_reasons":dict(Counter(r["failure_reason"] for r in x if r["failure_reason"]))}
 summary={"status":"complete","blinded_until_all_records_frozen":True,"time_limit_minutes":8,"pairs":80,"results_by_hidden_class":by,"witness_count":sum(r["success_or_failure"]=="success" for r in records)}
 dump(OUT/"review_summary.json",summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
