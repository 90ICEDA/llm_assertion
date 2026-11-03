from __future__ import annotations
import argparse,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from generate_pilot_v2_ast_smoke_v2 import allowed_fn,build_trie,sha
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1"; OOD=BASE/"frozen_ood_top1_v1"; MANIFEST=OOD/"query_manifest.json"; MODEL=ROOT/"outputs/checkpoints/Qwen3-8B"; OUT=OOD/"generations"; SEED=20260815
def atomic(p,x): p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+".tmp"); t.write_text(json.dumps(x,indent=2)+"\n"); os.replace(t,p)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--preflight-only",action="store_true"); ap.add_argument("--resume",action="store_true"); args=ap.parse_args(); manifest=json.loads(MANIFEST.read_text()); adapter=manifest["adapter"]
    if manifest["status"]!="frozen_before_any_phase_b_ood_generation" or len(manifest["records"])!=48 or not manifest["query_universe_and_prompts_unchanged"]: raise RuntimeError("unexpected OOD manifest")
    if sha(ROOT/adapter["adapter_path"]/"adapter_model.safetensors")!=adapter["adapter_sha256"]: raise RuntimeError("adapter hash mismatch")
    if args.preflight_only: print(json.dumps({"status":"pass","query_count":48,"generation_count":48,"manifest_sha256":sha(MANIFEST),"adapter_sha256":adapter["adapter_sha256"],"source_query_manifest_sha256":manifest["source_query_manifest_sha256"]},sort_keys=True)); return
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig
    torch.manual_seed(SEED); torch.cuda.manual_seed_all(SEED); tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True); tok.pad_token_id=tok.eos_token_id; quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16); base=AutoModelForCausalLM.from_pretrained(MODEL,quantization_config=quant,device_map={"":0},local_files_only=True,low_cpu_mem_usage=True); model=PeftModel.from_pretrained(base,ROOT/adapter["adapter_path"],is_trainable=False); model.eval(); completed=0
    for row in manifest["records"]:
        directory=OUT/row["case_id"]; evidence=directory/"evidence.json"
        if evidence.exists():
            old=json.loads(evidence.read_text()); valid=old.get("status")=="complete" and old.get("prompt_sha256")==row["prompt_sha256"] and old.get("adapter_sha256")==adapter["adapter_sha256"]
            if args.resume and valid: completed+=1; continue
            raise RuntimeError(f"refusing to regenerate: {evidence}")
        prompt=(ROOT/row["prompt_path"]).read_text(); inputs=tok(prompt,return_tensors="pt",add_special_tokens=False).to("cuda"); n=inputs.input_ids.shape[1]; trie=build_trie(tok,row["semantic_signals"]); began=time.perf_counter()
        with torch.inference_mode(): output=model.generate(**inputs,do_sample=False,num_return_sequences=1,max_new_tokens=128,eos_token_id=tok.eos_token_id,pad_token_id=tok.eos_token_id,prefix_allowed_tokens_fn=allowed_fn(trie,n),use_cache=True)
        generated=output[0,n:].tolist(); ended=bool(generated and generated[-1]==tok.eos_token_id); raw=tok.decode(generated[:-1] if ended else generated,skip_special_tokens=False); ast=json.loads(raw) if ended else None; directory.mkdir(parents=True); raw_path=directory/"raw_response.txt"; ast_path=directory/"ast.json"; raw_path.write_text(raw)
        if ast is not None: ast_path.write_text(json.dumps(ast,separators=(",",":")))
        record={"status":"complete","query_id":row["query_id"],"case_id":row["case_id"],"memberships":row["memberships"],"prompt_path":row["prompt_path"],"prompt_sha256":row["prompt_sha256"],"adapter_path":adapter["adapter_path"],"adapter_sha256":adapter["adapter_sha256"],"decode":manifest["decode"],"seed":SEED,"input_tokens":n,"output_tokens_including_eos":len(generated),"raw_response_sha256":sha(raw_path),"ast_sha256":sha(ast_path) if ast_path.exists() else None,"json_ast_extracted":ast is not None,"schema_keys_valid":isinstance(ast,dict) and tuple(ast)==("antecedent_signal","antecedent_polarity","consequent_signal","implication","relation"),"ended_on_eos":ended,"hit_max_new_tokens":len(generated)>=128,"generation_constraint":"strict_schema_trie","wall_clock_seconds":time.perf_counter()-began,"generated_utc":datetime.now(timezone.utc).isoformat()}; atomic(evidence,record); completed+=1; print(row["case_id"],completed,record["schema_keys_valid"],ended,flush=True)
    atomic(OOD/"generation_run_manifest.json",{"status":"complete","completed_generation_count":completed,"query_manifest_sha256":sha(MANIFEST),"adapter_sha256":adapter["adapter_sha256"],"completed_utc":datetime.now(timezone.utc).isoformat()}); print(json.dumps({"status":"complete","completed_generation_count":completed},sort_keys=True))
if __name__=="__main__": main()
