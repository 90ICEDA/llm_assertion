from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];V2=ROOT/"outputs/behavioral_preference_pilot_v2";TRAIN=V2/"formal_training_v2";OUT=V2/"ast_smoke_v1"
METHODS=("ordinary_sft","pass_count_dpo","scalar_score_dpo","random_probe_dominance_dpo","full_disagreement_dominance_dpo")
PARENTS=("case510_cc_spill_register_flush_push_priority","case133_prim_edge_negedge_missing","case478_axis_srl_register_ready_recovery")
EXPECTED={"ordinary_sft":"7c506d470ad678819ae19712c4249f9b3efb7e6ded2e6433b169df835edf1dd4","pass_count_dpo":"026857b563212f473ba53b0a902721f40646c7af68e7efe97d93feac9a247852","scalar_score_dpo":"ddb1a8553af2a67e693d7991390402da4ea6a30c0e38a8f30d0e4dee2e0cc3bb","random_probe_dominance_dpo":"e78a63f9729ee567cde17f5aec4d06840b02effdf1aed4fec2a7f474becdeb7f","full_disagreement_dominance_dpo":"d891f948172864072ef33d9599fef16a6a983737bb871267665d4f493ba0ae29"}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def extract(text):
 try:
  a=text.index('{'); obj,end=json.JSONDecoder().raw_decode(text[a:]);return obj,a+end
 except Exception:return None,None
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--resume',action='store_true');ap.add_argument('--preflight-only',action='store_true');args=ap.parse_args()
 adapters={}
 for m in METHODS:
  ck=(TRAIN/m/'latest_checkpoint.txt').read_text().strip();p=TRAIN/m/ck/'adapter_model.safetensors'
  if sha(p)!=EXPECTED[m]:raise RuntimeError(f'adapter hash mismatch {m}')
  adapters[m]=str((TRAIN/m/ck).relative_to(ROOT)).replace('\\','/')
 manifest={"status":"frozen_before_smoke_generation","parents":PARENTS,"methods":METHODS,"slots":8,"generation_count":120,"decode":{"do_sample":False,"temperature":0.0,"num_return_sequences":1,"max_new_tokens":128,"seed":20260815},"adapters":adapters,"adapter_hashes":EXPECTED}
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'smoke_manifest.json').write_text(json.dumps(manifest,indent=2)+"\n")
 if args.preflight_only:print(json.dumps({"status":"pass","generation_count":120,"manifest_sha256":sha(OUT/'smoke_manifest.json')}));return
 import torch
 from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig
 from peft import PeftModel
 model_path=ROOT/'outputs/checkpoints/Qwen3-8B';tok=AutoTokenizer.from_pretrained(model_path,local_files_only=True)
 quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
 for method in METHODS:
  base=AutoModelForCausalLM.from_pretrained(model_path,quantization_config=quant,device_map={'':0},local_files_only=True,low_cpu_mem_usage=True)
  model=PeftModel.from_pretrained(base,ROOT/adapters[method]);model.eval()
  for parent in PARENTS:
   original=(V2/'training_corpora_v1/prompts'/parent/'prompt.txt').read_text()
   for slot in range(1,9):
    d=OUT/'generations'/method/parent/f'slot_{slot:02d}';e=d/'evidence.json'
    if args.resume and e.is_file():continue
    d.mkdir(parents=True,exist_ok=True);prompt=original+f"Smoke diversity slot: {slot}/8. Return one valid object now.\n";(d/'prompt.txt').write_text(prompt)
    ids=tok(prompt,return_tensors='pt').to('cuda');beg=time.perf_counter()
    with torch.no_grad():out=model.generate(**ids,do_sample=False,num_return_sequences=1,max_new_tokens=128,pad_token_id=tok.eos_token_id)
    raw=tok.decode(out[0,ids.input_ids.shape[1]:],skip_special_tokens=True);(d/'raw_response.txt').write_text(raw)
    obj,end=extract(raw);valid=isinstance(obj,dict) and set(obj)=={"antecedent_signal","antecedent_polarity","consequent_signal","implication","relation"}
    if obj is not None:(d/'ast.json').write_text(json.dumps(obj,sort_keys=True)+"\n")
    evidence={"status":"complete","method":method,"parent":parent,"slot":slot,"adapter_sha256":EXPECTED[method],"prompt_sha256":sha(d/'prompt.txt'),"raw_sha256":sha(d/'raw_response.txt'),"json_ast_extracted":obj is not None,"schema_keys_valid":valid,"output_tokens":int(out.shape[1]-ids.input_ids.shape[1]),"wall_clock_seconds":time.perf_counter()-beg}
    e.write_text(json.dumps(evidence,indent=2)+"\n");print(method,parent,slot,valid,flush=True)
  del model,base;torch.cuda.empty_cache()
 print(json.dumps({"status":"complete","generation_count":len(list((OUT/'generations').rglob('evidence.json')))}))
if __name__=='__main__':main()
