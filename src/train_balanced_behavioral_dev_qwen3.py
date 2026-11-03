from __future__ import annotations

import argparse, hashlib, json, random, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1"
SCHEDULES, FROZEN = BASE / "token_schedules_v1", BASE / "balanced_behavioral_objective_v1_frozen.json"
MODEL, OUT = ROOT / "outputs/checkpoints/Qwen3-8B", BASE / "formal_training_dev_v1"
VARIANTS = ("anchor_10", "anchor_20", "anchor_25")

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def lines(p): return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
def ids(tok, text):
    value = tok.encode(text, add_special_tokens=False)
    return value.ids if hasattr(value, "ids") else value

def parts(tok, prompt, response):
    p, r = ids(tok, prompt), ids(tok, response)
    eos = getattr(tok, "eos_token_id", None)
    if eos is None and hasattr(tok, "token_to_id"): eos = tok.token_to_id("<|im_end|>")
    if eos is None: raise ValueError("supervised EOS unavailable")
    if not r or r[-1] != eos: r.append(eos)
    if not p or not r or len(r) > 512: raise ValueError("invalid frozen sequence")
    if len(p) + len(r) > 512: p = p[-(512-len(r)):]
    return p, r

def audit(variant, tok):
    path = SCHEDULES / f"{variant}.jsonl"; rows = lines(path)
    frozen, expected = load(FROZEN), load(SCHEDULES / "SHA256SUMS.json")
    if frozen["status"] != "frozen_before_any_balanced_objective_training": raise RuntimeError("objective not frozen")
    if sha(path) != expected[path.name]: raise RuntimeError("schedule hash mismatch")
    buckets, kinds, steps, parents = Counter(), Counter(), Counter(), set()
    truncations = 0; maximum = 0
    for n, row in enumerate(rows, 1):
        kind = row.get("record_type")
        if kind not in {"sft_anchor", "dpo_edge"}: raise ValueError(f"bad record type line {n}")
        expected_bucket = "anchor" if kind == "sft_anchor" else row["stratum"]
        if row.get("objective_bucket") != expected_bucket: raise ValueError(f"bad bucket line {n}")
        prompt = (ROOT / row["prompt_path"]).read_text(encoding="utf-8"); original = len(ids(tok, prompt)); cost = 0
        paths = [row["response_path"]] if kind == "sft_anchor" else [row["chosen_path"], row["rejected_path"]]
        for response_path in paths:
            p, r = parts(tok, prompt, (ROOT / response_path).read_text(encoding="utf-8"))
            cost += len(r); truncations += int(len(p) < original); maximum = max(maximum, len(p)+len(r))
        if cost != row["loss_tokens"]: raise ValueError(f"token mismatch line {n}: {cost} != {row['loss_tokens']}")
        loss_kind = "sft" if kind == "sft_anchor" else "dpo"
        buckets[row["objective_bucket"]] += cost; kinds[loss_kind] += cost; steps[loss_kind] += 1; parents.add(row["parent_bug_id"])
    total = sum(buckets.values())
    if total != 245760 or total != frozen["loss_token_budget_per_variant"]: raise RuntimeError(f"budget mismatch {total}")
    return rows, {"variant":variant,"seed":frozen["seed"],"schedule":str(path.relative_to(ROOT)).replace("\\","/"),
        "schedule_sha256":sha(path),"frozen_objective_sha256":sha(FROZEN),"steps":len(rows),"loss_token_budget":total,
        "bucket_tokens":dict(sorted(buckets.items())),"loss_type_steps":dict(sorted(steps.items())),
        "loss_type_tokens":dict(sorted(kinds.items())),"effective_parent_count":len(parents),"response_eos_required":True,
        "full_response_preserved":True,"prompt_truncation_count":truncations,"max_sequence_tokens_observed":maximum,
        "padding_policy":"batch_size_1; no padding; exact all-ones attention mask",
        "schedule_policy":"execute materialized rows exactly once in file order; no trainer resampling"}

def tensor(tok, prompt, response):
    p, r = parts(tok, prompt, response)
    return torch.tensor([p+r], dtype=torch.long, device="cuda"), len(p)
def logp(model, x, start):
    out=model(input_ids=x,attention_mask=torch.ones_like(x),use_cache=False); logits=out.logits[:,:-1,:]; labels=x[:,1:]
    values=F.log_softmax(logits.float(),dim=-1).gather(-1,labels.unsqueeze(-1)).squeeze(-1)[:,start-1:].sum(-1)
    del out,logits,labels; return values
def save(model,opt,out,step,meta):
    ckpt=out/f"checkpoint-{step:06d}"; ckpt.mkdir(parents=True,exist_ok=True); model.save_pretrained(ckpt,safe_serialization=True)
    torch.save(opt.state_dict(),ckpt/"optimizer.pt"); (ckpt/"state.json").write_text(json.dumps({**meta,"completed_steps":step},indent=2)+"\n")
    (out/"latest_checkpoint.txt").write_text(ckpt.name+"\n")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--variant",required=True,choices=VARIANTS); ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--resume",action="store_true"); ap.add_argument("--save-steps",type=int,default=500); args=ap.parse_args()
    from tokenizers import Tokenizer
    schedule,meta=audit(args.variant,Tokenizer.from_file(str(MODEL/"tokenizer.json")))
    if args.dry_run: print(json.dumps({**meta,"status":"dry_run_pass"},sort_keys=True)); return
    global torch,F
    import torch, torch.nn.functional as F
    from peft import LoraConfig,PeftModel,get_peft_model
    from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig
    out=OUT/args.variant; out.mkdir(parents=True,exist_ok=True); torch.manual_seed(meta["seed"]); random.seed(meta["seed"])
    tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True); quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
    base=AutoModelForCausalLM.from_pretrained(MODEL,quantization_config=quant,device_map={"":0},local_files_only=True,low_cpu_mem_usage=True)
    base.gradient_checkpointing_enable(); base.enable_input_require_grads(); base.config.use_cache=False; start=0; resume=None
    if args.resume and (out/"latest_checkpoint.txt").is_file():
        resume=out/(out/"latest_checkpoint.txt").read_text().strip(); model=PeftModel.from_pretrained(base,resume,is_trainable=True); start=load(resume/"state.json")["completed_steps"]
    else: model=get_peft_model(base,LoraConfig(r=8,lora_alpha=16,lora_dropout=.05,bias="none",task_type="CAUSAL_LM",target_modules=["q_proj","v_proj"]))
    opt=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=1e-4)
    if resume: opt.load_state_dict(torch.load(resume/"optimizer.pt",map_location="cpu",weights_only=True))
    began=time.perf_counter(); log_file=out/"train_log.jsonl"
    for step in range(start,len(schedule)):
        row=schedule[step]; prompt=(ROOT/row["prompt_path"]).read_text(encoding="utf-8"); opt.zero_grad(set_to_none=True)
        if row["record_type"]=="sft_anchor":
            x,s=tensor(tok,prompt,(ROOT/row["response_path"]).read_text(encoding="utf-8")); loss=-logp(model,x,s).mean()/(x.shape[1]-s); loss.backward(); kind="sft"
        else:
            c,cs=tensor(tok,prompt,(ROOT/row["chosen_path"]).read_text(encoding="utf-8")); r,rs=tensor(tok,prompt,(ROOT/row["rejected_path"]).read_text(encoding="utf-8"))
            with torch.no_grad(),model.disable_adapter(): rc,rr=logp(model,c,cs).detach(),logp(model,r,rs).detach()
            torch.cuda.empty_cache()
            with torch.no_grad():
                pc,pr=logp(model,c,cs).detach(),logp(model,r,rs).detach(); margin=(pc-pr)-(rc-rr); loss=-F.logsigmoid(.1*margin).mean(); coef=-.1*torch.sigmoid(-.1*margin)
            torch.cuda.empty_cache(); (coef*logp(model,c,cs)).sum().backward(); torch.cuda.empty_cache(); (-coef*logp(model,r,rs)).sum().backward(); kind="dpo"
        if not all(p.grad is None or bool(torch.isfinite(p.grad).all()) for p in model.parameters() if p.requires_grad): raise FloatingPointError(f"non-finite gradient step {step+1}")
        torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad),1.0); opt.step()
        record={"step":step+1,"loss":float(loss.detach()),"loss_type":kind,"objective_bucket":row["objective_bucket"],"record_id":row.get("pair_id",row.get("example_id")),"loss_tokens":row["loss_tokens"],"elapsed_seconds":time.perf_counter()-began,"cuda_peak_allocated_mib":round(torch.cuda.max_memory_allocated()/1048576,1)}
        with log_file.open("a",encoding="utf-8") as f: f.write(json.dumps(record,sort_keys=True)+"\n")
        if (step+1)%args.save_steps==0 or step+1==len(schedule): save(model,opt,out,step+1,meta)
    result={**meta,"status":"pass","completed_steps":len(schedule),"wall_clock_seconds":time.perf_counter()-began,"cuda_peak_allocated_mib":round(torch.cuda.max_memory_allocated()/1048576,1),"cuda_peak_reserved_mib":round(torch.cuda.max_memory_reserved()/1048576,1)}
    (out/"training_result.json").write_text(json.dumps(result,indent=2)+"\n"); print(json.dumps(result,sort_keys=True))
if __name__=="__main__": main()
