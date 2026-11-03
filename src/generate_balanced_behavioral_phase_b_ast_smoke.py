from __future__ import annotations
import argparse,json,time
from pathlib import Path
from generate_pilot_v2_ast_smoke_v2 import KEYS,allowed_fn,build_trie,sha,signals_from_prompt
ROOT=Path(__file__).resolve().parents[1]; V2=ROOT/"outputs/behavioral_preference_pilot_v2"; DATA=V2/"training_corpora_v2"; BASE=V2/"balanced_behavioral_objective_v1/phase_b_refit_all30_v1"; ADAPTER=BASE/"final_adapter_manifest.json"; OUT=BASE/"ast_smoke_v1"
PARENTS=("case133_prim_edge_negedge_missing","case478_axis_srl_register_ready_recovery","case510_cc_spill_register_flush_push_priority")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--resume",action="store_true"); ap.add_argument("--preflight-only",action="store_true"); args=ap.parse_args(); adapter=json.loads(ADAPTER.read_text())
    if adapter["status"]!="frozen_before_phase_b_ast_smoke" or sha(ROOT/adapter["adapter_path"]/"adapter_model.safetensors")!=adapter["adapter_sha256"]: raise RuntimeError("Phase B adapter freeze mismatch")
    manifest={"status":"frozen_before_phase_b_smoke_generation","version":"phase_b_ast_smoke_v1_strict_trie_eos","parents":list(PARENTS),"design_classes":["temporal_edge","ready_valid_backpressure","flush_push_priority"],"variant":"anchor_20_all30","slots":8,"generation_count":24,"decode":{"do_sample":False,"temperature":0.0,"num_return_sequences":1,"max_new_tokens":128,"seed":20260815},"constraint":"complete schema-valid canonical JSON trie; exactly five keys; forced EOS after closing brace","adapter_manifest_sha256":sha(ADAPTER),"adapter":adapter}
    OUT.mkdir(parents=True,exist_ok=True); manifest_path=OUT/"smoke_manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text())!=manifest: raise RuntimeError("refusing to change Phase B smoke manifest")
    manifest_path.write_text(json.dumps(manifest,indent=2)+"\n")
    if args.preflight_only: print(json.dumps({"status":"pass","generation_count":24,"manifest_sha256":sha(manifest_path),"adapter_sha256":adapter["adapter_sha256"]},sort_keys=True)); return
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig
    model_path=ROOT/"outputs/checkpoints/Qwen3-8B"; tok=AutoTokenizer.from_pretrained(model_path,local_files_only=True); quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
    base=AutoModelForCausalLM.from_pretrained(model_path,quantization_config=quant,device_map={"":0},local_files_only=True,low_cpu_mem_usage=True); model=PeftModel.from_pretrained(base,ROOT/adapter["adapter_path"]); model.eval()
    for parent in PARENTS:
        original=(DATA/"prompts"/parent/"prompt.txt").read_text(); trie=build_trie(tok,signals_from_prompt(original))
        for slot in range(1,9):
            directory=OUT/"generations"/"anchor_20_all30"/parent/f"slot_{slot:02d}"; evidence=directory/"evidence.json"
            if evidence.exists():
                if args.resume: continue
                raise RuntimeError(f"refusing to regenerate: {evidence}")
            directory.mkdir(parents=True,exist_ok=True); prompt=original+f"Smoke diversity slot: {slot}/8. Return one valid object now.\n"; (directory/"prompt.txt").write_text(prompt); inputs=tok(prompt,return_tensors="pt").to("cuda"); n=inputs.input_ids.shape[1]; began=time.perf_counter()
            with torch.inference_mode(): output=model.generate(**inputs,do_sample=False,num_return_sequences=1,max_new_tokens=128,eos_token_id=tok.eos_token_id,pad_token_id=tok.eos_token_id,prefix_allowed_tokens_fn=allowed_fn(trie,n))
            generated=output[0,n:].tolist(); ended=bool(generated and generated[-1]==tok.eos_token_id); raw=tok.decode(generated[:-1] if ended else generated,skip_special_tokens=False); (directory/"raw_response.txt").write_text(raw)
            try: ast=json.loads(raw)
            except json.JSONDecodeError: ast=None
            valid=isinstance(ast,dict) and tuple(ast)==KEYS
            if valid: (directory/"ast.json").write_text(json.dumps(ast,separators=(",",":")))
            record={"status":"complete","variant":"anchor_20_all30","parent":parent,"slot":slot,"adapter_sha256":adapter["adapter_sha256"],"prompt_sha256":sha(directory/"prompt.txt"),"raw_sha256":sha(directory/"raw_response.txt"),"json_ast_extracted":ast is not None,"schema_keys_valid":valid,"ended_on_eos":ended,"output_tokens_including_eos":len(generated),"hit_max_new_tokens":len(generated)>=128,"generation_constraint":"strict_schema_trie","wall_clock_seconds":time.perf_counter()-began}; evidence.write_text(json.dumps(record,indent=2)+"\n"); print(parent,slot,valid,ended,flush=True)
    print(json.dumps({"status":"complete","generation_count":len(list((OUT/"generations").rglob("evidence.json")))}))
if __name__=="__main__": main()
