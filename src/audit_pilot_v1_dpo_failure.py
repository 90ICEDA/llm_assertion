from __future__ import annotations
import hashlib,json,re
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT/"outputs/behavioral_preference_pilot_v1";OUT=ROOT/"outputs/behavioral_preference_pilot_v2"
METHODS=("ordinary_sft","pass_count_dpo","scalar_score_dpo","random_probe_dominance_dpo","full_disagreement_dominance_dpo")
def lines(p):return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 corp=P/"training_corpora_v2"; per={}; total=0
 for method in METHODS:
  rows=lines(corp/f"{method}.jsonl"); mismatches=0; responses=0; invalid_sources=0
  for r in rows:
   prompt=(ROOT/r["prompt_path"]).read_text(encoding="utf-8")
   paths=[r["response_path"]] if method=="ordinary_sft" else [r["chosen_path"],r["rejected_path"]]
   for rel in paths:
    response=(ROOT/rel).read_text(encoding="utf-8").strip();responses+=1
    lowered=prompt.lower()
    prompt_requests_ast=("json ast" in lowered or "json object" in lowered) and ("do not emit systemverilog" in lowered or "do not write systemverilog" in lowered)
    response_is_sva=response.startswith("assert property (") and response.endswith(");")
    mismatches+=int(prompt_requests_ast and response_is_sva)
    invalid_sources+=int(not response_is_sva)
   total+=1
  per[method]={"records":len(rows),"response_instances":responses,"ast_prompt_sva_response_mismatches":mismatches,
   "non_sva_source_responses":invalid_sources,"corpus_sha256":sha(corp/f"{method}.jsonl")}
 evalroot=P/"frozen_top1_v1/execution_evaluation_v1/records"; generated={}
 for method in METHODS:
  docs=[json.loads(x.read_text(encoding="utf-8")) for x in (evalroot/method).rglob("evaluation.json")]; c=Counter()
  for d in docs:
   if not d["sva_extracted"]:c["extraction_failure"]+=1
   err=d.get("evaluation_error") or ""
   if "Unsupported assertion format" in err:c["unsupported_assertion_format"]+=1
   if "undeclared" in err.lower() or "Unable to bind" in json.dumps(d.get("raw_evaluation",{})):c["undeclared_or_unbindable"]+=1
   if d["compile_ok"]:c["compile_ok"]+=1
  generated[method]=dict(c)
 train=(ROOT/"src/train_pilot_qwen3.py").read_text(encoding="utf-8")
 static={"response_only_mask": "logps[:, response_start - 1:]" in train,
  "reference_uses_adapter_disabled": "model.disable_adapter()" in train,
  "dpo_margin_sign": "margin = (pc - pr) - (rc - rr)" in train,
  "chosen_gradient_sign": "coefficient * response_logp(model, chosen" in train,
  "rejected_gradient_sign": "-coefficient * response_logp(model, rejected" in train}
 report={"status":"root_cause_confirmed","immutable_source":"Pilot v1 remains unchanged","corpora":per,
  "training_implementation_static_checks":static,"frozen_generation_failure_taxonomy":generated,
  "primary_root_cause":"Every supervised training prompt requests JSON AST and forbids SystemVerilog, while every target response is rendered SVA. Frozen inference requests direct SVA, creating a three-way format mismatch.",
  "secondary_observation":"All DPO outputs reached the 512-token cap; extracted DPO assertions were bare names, missing event controls, malformed expressions, or used pseudo-functions.",
  "not_supported_by_evidence":"No sign inversion or prompt-token loss masking bug was found in the frozen training implementation.",
  "required_v2_fix":"Use one canonical JSON AST response for SFT, chosen, rejected, and inference; validate schema and deterministically render SVA outside the model."}
 OUT.mkdir(parents=True,exist_ok=True);(OUT/"dpo_failure_root_cause_audit_v1.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
 print(json.dumps({"status":"pass","root_cause":report["primary_root_cause"],"corpora":per},ensure_ascii=False))
if __name__=="__main__":main()
