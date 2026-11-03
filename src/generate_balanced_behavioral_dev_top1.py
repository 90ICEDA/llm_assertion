from __future__ import annotations
import argparse,json,os,platform,sys,time
from datetime import datetime,timezone
from pathlib import Path
from generate_pilot_v2_ast_smoke_v2 import allowed_fn,build_trie,sha

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1"
DEV=BASE/"dev_top1_v1"; MANIFEST=DEV/"query_manifest.json"; ADAPTERS=BASE/"formal_training_dev_v1/final_adapter_manifest.json"; MODEL=ROOT/"outputs/checkpoints/Qwen3-8B"; OUT=DEV/"generations"; SEED=20260815
def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(value,indent=2)+"\n"); os.replace(tmp,path)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--preflight-only",action="store_true"); ap.add_argument("--resume",action="store_true"); args=ap.parse_args()
    manifest=json.loads(MANIFEST.read_text()); adapters=json.loads(ADAPTERS.read_text())["methods"]
    if manifest["status"]!="frozen_before_any_dev_generation" or len(manifest["records"])!=6 or len(adapters)!=3: raise RuntimeError("unexpected frozen dev inputs")
    for name,row in adapters.items():
        if sha(ROOT/row["adapter_path"]/"adapter_model.safetensors")!=row["adapter_sha256"]: raise RuntimeError(f"adapter hash mismatch: {name}")
    if args.preflight_only:
        print(json.dumps({"status":"pass","query_count":6,"adapter_count":3,"generation_count":18,"manifest_sha256":sha(MANIFEST),"adapter_manifest_sha256":sha(ADAPTERS)},sort_keys=True)); return
    import torch,transformers
    from peft import PeftModel,__version__ as peft_version
    from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig
    torch.manual_seed(SEED); torch.cuda.manual_seed_all(SEED); tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True); tok.pad_token_id=tok.eos_token_id
    run={"status":"running","seed":SEED,"query_manifest_sha256":sha(MANIFEST),"adapter_manifest_sha256":sha(ADAPTERS),"expected_generation_count":18,"command":[sys.executable,*sys.argv],"python":platform.python_version(),"torch":torch.__version__,"transformers":transformers.__version__,"peft":peft_version,"gpu":torch.cuda.get_device_name(0),"once_only_policy":"valid evidence skipped under --resume; never regenerated"}; atomic(DEV/"generation_run_manifest.json",run)
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16); completed=0
    for variant,adapter in adapters.items():
        base=AutoModelForCausalLM.from_pretrained(MODEL,quantization_config=quant,device_map={"":0},local_files_only=True,low_cpu_mem_usage=True); model=PeftModel.from_pretrained(base,ROOT/adapter["adapter_path"],is_trainable=False); model.eval()
        for row in manifest["records"]:
            directory=OUT/variant/row["case_id"]; evidence=directory/"evidence.json"
            if evidence.exists():
                old=json.loads(evidence.read_text()); valid=old.get("status")=="complete" and old.get("prompt_sha256")==row["prompt_sha256"] and old.get("adapter_sha256")==adapter["adapter_sha256"]
                if args.resume and valid: completed+=1; continue
                raise RuntimeError(f"refusing to regenerate: {evidence}")
            prompt=(ROOT/row["prompt_path"]).read_text(); inputs=tok(prompt,return_tensors="pt",add_special_tokens=False).to("cuda"); n=inputs.input_ids.shape[1]; trie=build_trie(tok,row["semantic_signals"]); began=time.perf_counter()
            with torch.inference_mode(): output=model.generate(**inputs,do_sample=False,num_return_sequences=1,max_new_tokens=128,eos_token_id=tok.eos_token_id,pad_token_id=tok.eos_token_id,prefix_allowed_tokens_fn=allowed_fn(trie,n),use_cache=True)
            generated=output[0,n:].tolist(); ended=bool(generated and generated[-1]==tok.eos_token_id); raw=tok.decode(generated[:-1] if ended else generated,skip_special_tokens=False); ast=json.loads(raw) if ended else None
            directory.mkdir(parents=True,exist_ok=True); raw_path=directory/"raw_response.txt"; ast_path=directory/"ast.json"; raw_path.write_text(raw)
            if ast is not None: ast_path.write_text(json.dumps(ast,separators=(",",":")))
            record={"status":"complete","variant":variant,"query_id":row["query_id"],"case_id":row["case_id"],"prompt_path":row["prompt_path"],"prompt_sha256":row["prompt_sha256"],"adapter_path":adapter["adapter_path"],"adapter_sha256":adapter["adapter_sha256"],"decode":manifest["decode"],"seed":SEED,"input_tokens":n,"output_tokens_including_eos":len(generated),"raw_response_sha256":sha(raw_path),"ast_sha256":sha(ast_path) if ast_path.exists() else None,"json_ast_extracted":ast is not None,"schema_keys_valid":isinstance(ast,dict) and tuple(ast)==("antecedent_signal","antecedent_polarity","consequent_signal","implication","relation"),"ended_on_eos":ended,"hit_max_new_tokens":len(generated)>=128,"generation_constraint":"strict_schema_trie","wall_clock_seconds":time.perf_counter()-began,"generated_utc":datetime.now(timezone.utc).isoformat()}; atomic(evidence,record); completed+=1; print(variant,row["case_id"],completed,record["schema_keys_valid"],ended,flush=True)
        del model,base; torch.cuda.empty_cache()
    run.update({"status":"complete","completed_generation_count":completed,"completed_utc":datetime.now(timezone.utc).isoformat()}); atomic(DEV/"generation_run_manifest.json",run); print(json.dumps({"status":"complete","completed_generation_count":completed},sort_keys=True))
if __name__=="__main__": main()
