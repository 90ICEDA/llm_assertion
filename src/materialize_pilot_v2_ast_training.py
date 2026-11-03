from __future__ import annotations
import csv,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];V1=ROOT/"outputs/behavioral_preference_pilot_v1";V2=ROOT/"outputs/behavioral_preference_pilot_v2";DATA=V2/"training_corpora_v1"
METHODS=("ordinary_sft","pass_count_dpo","scalar_score_dpo","random_probe_dominance_dpo","full_disagreement_dominance_dpo")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def writej(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
def readl(p):return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def main():
 evidence={}; parent_meta={}
 with (V1/"selected_train_parents.csv").open(encoding="utf-8-sig",newline="") as f:
  parent_meta={x["parent_bug_id"]:x for x in csv.DictReader(f)}
 for p in (V1/"sequential_generation_v3_pilot30").rglob("evidence.json"):
  d=json.loads(p.read_text(encoding="utf-8")); cid=f"{d['parent_bug_id']}__v3_slot_{int(d['slot']):02d}"; evidence[cid]=(d,p)
 if len(evidence)!=240:raise RuntimeError(f"expected 240 AST evidence, got {len(evidence)}")
 parent_prompts={}
 for parent,row in parent_meta.items():
  items=[d for d,_ in evidence.values() if d["parent_bug_id"]==parent]; first=items[0]
  signals=[x for x in first["signals"] if x not in {first.get("clock"),first.get("reset")}]
  source=(ROOT/row["dataset_root"]/row["case_id"]); spec=next(x for x in (source/"spec.md",source/"experiment/spec.txt",source/"spec.txt") if x.is_file()).read_text(encoding="utf-8").strip()
  prompt=("Return exactly one compact JSON object and no prose or SystemVerilog.\n"
   'Keys in this exact order: "antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation".\n'
   f"antecedent_signal and consequent_signal must be one of: {', '.join(signals)}.\n"
   'antecedent_polarity must be "high" or "low". implication must be "|->" or "|=>". '
   'relation must be "high", "low", "equal", or "not_equal".\n'
   f"Parent: {parent}\nProject: {row['source_project']}\nBug family: {row['bug_family']}\nSpecification: {spec}\n")
  pp=DATA/"prompts"/parent/"prompt.txt";pp.parent.mkdir(parents=True,exist_ok=True);pp.write_text(prompt,encoding="utf-8")
  parent_prompts[parent]=str(pp.relative_to(ROOT)).replace('\\','/')
 response_paths={}
 for cid,(d,src) in evidence.items():
  ast=d["ast"]; required={"antecedent_signal","antecedent_polarity","consequent_signal","implication","relation"}
  if set(ast)!=required:raise RuntimeError(f"AST schema mismatch {cid}: {set(ast)}")
  rp=DATA/"responses"/f"{cid}.json";writej(rp,{k:ast[k] for k in ("antecedent_signal","antecedent_polarity","consequent_signal","implication","relation")});response_paths[cid]=str(rp.relative_to(ROOT)).replace('\\','/')
 source=V1/"training_corpora_v2"; counts={}
 for method in METHODS:
  old=readl(source/f"{method}.jsonl");new=[]
  for r in old:
   parent=r["parent_bug_id"];base={k:v for k,v in r.items() if k not in ("prompt_path","response_path","chosen_path","rejected_path")};base["prompt_path"]=parent_prompts[parent]
   if method=="ordinary_sft":base["response_path"]=response_paths[r["example_id"]]
   else:base["chosen_path"]=response_paths[r["chosen_id"]];base["rejected_path"]=response_paths[r["rejected_id"]]
   new.append(base)
  out=DATA/f"{method}.jsonl";out.parent.mkdir(parents=True,exist_ok=True);out.write_text(''.join(json.dumps(x,sort_keys=True,ensure_ascii=False)+'\n' for x in new),encoding="utf-8");counts[method]=len(new)
 frozen={"status":"frozen_before_pilot_v2_training","version":"pilot_v2_canonical_ast","seed":20260815,"model":"outputs/checkpoints/Qwen3-8B","loss_token_budget_per_method":245760,"budget_epoch_count":1,"max_sequence_tokens":512,"loss_token_accounting":"SFT=AST response tokens; DPO=chosen+rejected AST response tokens; no padding or repetition","canonical_output":"JSON AST only; deterministic renderer outside model","shared_qlora":{"bits":4,"quant":"nf4","double_quant":True,"lora_r":8,"lora_alpha":16,"lora_dropout":0.05,"targets":["q_proj","v_proj"]},"optimizer":{"name":"AdamW","lr":0.0001,"beta":0.1},"immutable_v1_probe_manifest_sha256":sha(V1/"behavioral_probes_v3/probe_manifest.json")}
 (DATA/"formal_training_v2_frozen.json").write_text(json.dumps(frozen,indent=2)+"\n",encoding="utf-8")
 hashes={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted(DATA.rglob('*')) if p.is_file()};(DATA/"SHA256SUMS.json").write_text(json.dumps(hashes,indent=2)+"\n",encoding="utf-8")
 audit={"status":"pass","parents":len(parent_prompts),"candidate_asts":len(response_paths),"corpora":counts,"all_prompts_request_json_ast":True,"all_responses_json_ast":True,"v1_files_written":False};(DATA/"materialization_audit.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8");print(json.dumps(audit))
if __name__=="__main__":main()
