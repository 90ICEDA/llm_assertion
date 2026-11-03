#!/usr/bin/env python3
"""Re-run only missing candidate×probe verdicts listed by the order audit."""
import csv, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src import behavioral_preference_v3_probes as bp

PARENT="case465_axis_srl_fifo_simultaneous_occupancy"
MISSING=ROOT/"deliverables/probe_order_sensitivity_20260829/cache_inconsistencies.csv"

def main():
    rows=list(csv.DictReader(MISSING.open(encoding="utf-8-sig",newline="")))
    rows=[r for r in rows if r["issue"]=="missing_verdict"]
    if not rows:
        print(json.dumps({"status":"nothing_missing","rerun_count":0}));return
    if {r["parent_id"] for r in rows}!={PARENT}:raise RuntimeError("unexpected parent in missing list")
    gen=ROOT/"outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30"/PARENT
    evidences={f"{PARENT}__v3_slot_{slot:02d}":json.loads((gen/f"slot_{slot:02d}/attempt_01/evidence.json").read_text(encoding="utf-8")) for slot in range(1,9)}
    probes={x["probe_id"]:x for x in json.loads((bp.OUT/PARENT/"probe_pool.json").read_text(encoding="utf-8"))["probes"]}
    correct,buggy,_=bp.locate_sources(next(iter(evidences.values())))
    done=[];verified=[]
    for r in rows:
        target=bp.OUT/PARENT/"runs"/r["probe_id"]/r["candidate_id"]/"result.json"
        if target.exists():
            d=json.loads(target.read_text(encoding="utf-8"));verified.append({"probe_id":r["probe_id"],"candidate_id":r["candidate_id"],"executable":d["executable"],"fp":d["fp"],"tp":d["tp"]})
            continue
        result=bp.run_candidate(bp.OUT/PARENT,probes[r["probe_id"]],evidences[r["candidate_id"]],correct,buggy)
        done.append({"probe_id":r["probe_id"],"candidate_id":r["candidate_id"],"executable":result["executable"],"fp":result["fp"],"tp":result["tp"]})
    log=ROOT/"deliverables/probe_order_sensitivity_20260829/formal_repair_log.json"
    log.write_text(json.dumps({"status":"complete","requested_missing_count":len(rows),"rerun_in_this_invocation":len(done),"verified_present_count":len(verified)+len(done),"rows":verified+done},indent=2),encoding="utf-8")
    print(json.dumps({"status":"complete","rerun_in_this_invocation":len(done),"verified_present_count":len(verified)+len(done)}))
if __name__=="__main__":main()
