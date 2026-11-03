#!/usr/bin/env python3
"""Freeze a balanced, blinded 60 equal-signature + 20 control-pair review."""
from __future__ import annotations
import csv, hashlib, json, os, random, re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"outputs/behavioral_preference_pilot_v1"
OUT=ROOT/"deliverables/manual_separability_review_20260829"
SEED=20260829
def lp(p):
 s=str(Path(p).resolve());return "\\\\?\\"+s if os.name=="nt" else s
def load(p):
 with open(lp(p),encoding="utf-8-sig") as f:return json.load(f)
def stable(*x):return hashlib.sha256("\x1f".join(map(str,x)).encode()).hexdigest()[:24]
def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/"blinded_packets").mkdir(exist_ok=True)
 train=list(csv.DictReader((BASE/"selected_train_parents.csv").open(encoding="utf-8-sig",newline="")))
 meta={x["parent_bug_id"]:x for x in train};equal={};resolved={};evidence={}
 for parent in sorted(meta):
  cs=[]; sig={}
  for slot in range(1,9):
   e=load(BASE/f"sequential_generation_v3_pilot30/{parent}/slot_{slot:02d}/attempt_01/evidence.json")
   cid=f"{parent}__v3_slot_{slot:02d}";cs.append(cid);evidence[cid]=e;sig[cid]=[]
  for q in range(64):
   pid=f"{parent}__probe_{q:03d}"
   for cid in cs:
    d=load(BASE/f"behavioral_probes_v3/{parent}/runs/{pid}/{cid}/result.json");sig[cid].append((bool(d["fp"]),bool(d["tp"])))
  eq=[];di=[]
  for a,b in combinations(cs,2):
   item=(stable("manual_pair",parent,*sorted((a,b))),a,b)
   (eq if sig[a]==sig[b] else di).append(item)
  equal[parent]=sorted(eq,key=lambda x:stable(SEED,*x));resolved[parent]=sorted(di,key=lambda x:stable(SEED,*x))
 # Exactly two equal-signature pairs per parent; controls cover 20 distinct parents.
 selected=[]
 for parent in sorted(meta):selected += [(parent,*x,"equal_signature") for x in equal[parent][:2]]
 control_parents=sorted(meta,key=lambda p:stable(SEED,"control_parent",p))[:20]
 for parent in control_parents:selected.append((parent,*resolved[parent][0],"control_resolved"))
 rng=random.Random(SEED);rng.shuffle(selected)
 seal=[];index=[]
 for n,(parent,pid,a,b,label) in enumerate(selected,1):
  review_id=f"review_{n:03d}";flip=random.Random(SEED^n).randrange(2)
  A,B=(b,a) if flip else (a,b);ea,eb=evidence[A],evidence[B]
  case_root=Path(ea["runs"]["correct"]["command"][-3]).parent
  # Store only neutral context; source labels and experiment policy are absent.
  packet={"review_id":review_id,"pair_id":pid,"parent_id":parent,"time_limit_minutes":8,
   "clock":ea.get("clock"),"reset":ea.get("reset"),"interface_signals":ea.get("signals",[]),
   "environment_assumptions":["Use the existing parent testbench/interface contract.","Do not drive DUT outputs.","Do not add assumptions not justified by RTL or the existing environment."],
   "candidate_a":{"property_ir":ea.get("ast"),"sva":ea.get("sva")},"candidate_b":{"property_ir":eb.get("ast"),"sva":eb.get("sva")},
   "context_paths":{"correct_rtl":str(case_root/"correct.v"),"buggy_rtl":str(case_root/"buggy.v"),"primary_tb":str(case_root/"tb.v"),"heldout_tb":str(case_root/"tb_holdout.v"),"mutation_diff":str(case_root/"mutation.diff")}}
  (OUT/"blinded_packets"/f"{review_id}.json").write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding="utf-8")
  index.append({"review_id":review_id,"pair_id":pid,"parent_id":parent,"bug_family":meta[parent]["bug_family"],"packet_path":f"blinded_packets/{review_id}.json"})
  seal.append({"review_id":review_id,"pair_id":pid,"parent_id":parent,"candidate_a_id":A,"candidate_b_id":B,"sampling_class":label,"source_candidate_a_path":ea["response_path"],"source_candidate_b_path":eb["response_path"]})
 def wc(path,data,fields):
  with path.open("w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
 wc(OUT/"blinded_index.csv",index,list(index[0]));wc(OUT/"sealed_sampling_map.csv",seal,list(seal[0]))
 protocol={"status":"frozen","seed":SEED,"review_pairs":80,"equal_signature_pairs":60,"hidden_controls":20,"equal_sampling":"2 per each of 30 parents","control_sampling":"1 per each of 20 parents","time_limit_minutes_per_pair":8,"blinded_fields":["candidate source/model","input representation","probe strategy","current classification","control identity"],"success_requirements":["compile","no unjustified assumption","reachable","different verdict/behavior","replayable witness"]}
 (OUT/"review_protocol.json").write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(protocol,ensure_ascii=False))
if __name__=="__main__":main()
