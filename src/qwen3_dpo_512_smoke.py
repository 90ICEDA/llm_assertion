from __future__ import annotations

import hashlib
import json
import time
import traceback
from pathlib import Path

import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "outputs/checkpoints/Qwen3-8B"
PAIR_FILE = ROOT / "outputs/behavioral_preference_pilot_v1/dominance_pairs_v3/disagreement_guided_dominance_pairs.jsonl"
OUT = ROOT / "outputs/behavioral_preference_pilot_v1/training_dpo_512_smoke_r8_qv_sequential_no_fp32_cast.json"
SEED = 20260815
TOTAL_TOKENS = 512
RESPONSE_TOKENS = 32
PROMPT_TOKENS = TOTAL_TOKENS - RESPONSE_TOKENS
BETA = 0.1


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def exact(ids: list[int], length: int) -> list[int]:
    if not ids:
        raise ValueError("cannot expand an empty token sequence")
    return (ids * ((length + len(ids) - 1) // len(ids)))[:length]


def sequence_logp(model, input_ids: torch.Tensor, response_start: int) -> torch.Tensor:
    output = model(input_ids=input_ids, attention_mask=torch.ones_like(input_ids), use_cache=False)
    logits = output.logits[:, :-1, :]
    labels = input_ids[:, 1:]
    token_logps = F.log_softmax(logits.float(), dim=-1).gather(-1, labels.unsqueeze(-1)).squeeze(-1)
    # labels index response_start-1 predicts the first response token.
    value = token_logps[:, response_start - 1:].sum(dim=-1)
    del output, logits, labels, token_logps
    return value


def write(record: dict) -> None:
    OUT.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    torch.manual_seed(SEED)
    started = time.perf_counter()
    pair = json.loads(PAIR_FILE.read_text(encoding="utf-8").splitlines()[0])
    prompt_path = ROOT / pair["chosen_prompt_path"]
    chosen_path = ROOT / pair["chosen_sva_path"]
    rejected_path = ROOT / pair["rejected_sva_path"]
    record = {
        "status": "running",
        "purpose": "representative 512-token exact sequential-gradient DPO chosen/rejected memory and optimizer smoke",
        "seed": SEED,
        "pair_id": pair["pair_id"],
        "pair_file": str(PAIR_FILE.relative_to(ROOT)).replace("\\", "/"),
        "pair_file_sha256": sha(PAIR_FILE),
        "prompt_path": pair["chosen_prompt_path"], "prompt_sha256": sha(prompt_path),
        "chosen_sva_path": pair["chosen_sva_path"], "chosen_sva_sha256": sha(chosen_path),
        "rejected_sva_path": pair["rejected_sva_path"], "rejected_sva_sha256": sha(rejected_path),
        "total_tokens_each": TOTAL_TOKENS,
        "prompt_tokens_each": PROMPT_TOKENS,
        "response_tokens_each": RESPONSE_TOKENS,
        "construction": "real prompt and real SVA token IDs repeated then deterministically truncated to exact stress-test lengths; all 512 positions attended",
        "beta": BETA,
        "reference": "same quantized base model with LoRA adapter disabled; sequential no-grad reference forwards",
        "gradient_schedule": "compute scalar DPO derivative at current parameters, then exact chosen and rejected gradient contributions in separate recomputed forwards",
    }
    write(record)
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
        prompt_ids = exact(tokenizer.encode(prompt_path.read_text(encoding="utf-8"), add_special_tokens=False), PROMPT_TOKENS)
        chosen_ids = exact(tokenizer.encode(chosen_path.read_text(encoding="utf-8"), add_special_tokens=False), RESPONSE_TOKENS)
        rejected_ids = exact(tokenizer.encode(rejected_path.read_text(encoding="utf-8"), add_special_tokens=False), RESPONSE_TOKENS)
        chosen = torch.tensor([prompt_ids + chosen_ids], dtype=torch.long, device="cuda")
        rejected = torch.tensor([prompt_ids + rejected_ids], dtype=torch.long, device="cuda")
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
        model = AutoModelForCausalLM.from_pretrained(MODEL, quantization_config=quant, device_map={"": 0},
                                                     local_files_only=True, low_cpu_mem_usage=True)
        # Avoid PEFT's global non-int8 FP32 cast: on this 8 GiB device the
        # large vocabulary head alone makes that preparation step OOM.
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
        model.config.use_cache = False
        lora = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                          target_modules=["q_proj", "v_proj"])
        model = get_peft_model(model, lora)
        optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=1e-4)
        with torch.no_grad(), model.disable_adapter():
            ref_chosen = sequence_logp(model, chosen, PROMPT_TOKENS).detach()
            ref_rejected = sequence_logp(model, rejected, PROMPT_TOKENS).detach()
        torch.cuda.empty_cache()
        with torch.no_grad():
            policy_chosen_value = sequence_logp(model, chosen, PROMPT_TOKENS).detach()
            policy_rejected_value = sequence_logp(model, rejected, PROMPT_TOKENS).detach()
            logits = (policy_chosen_value - policy_rejected_value) - (ref_chosen - ref_rejected)
            loss = -F.logsigmoid(BETA * logits).mean()
            # d loss / d (policy_chosen - policy_rejected)
            coefficient = -BETA * torch.sigmoid(-BETA * logits)
        torch.cuda.empty_cache()
        policy_chosen = sequence_logp(model, chosen, PROMPT_TOKENS)
        (coefficient * policy_chosen).sum().backward()
        del policy_chosen
        torch.cuda.empty_cache()
        policy_rejected = sequence_logp(model, rejected, PROMPT_TOKENS)
        (-coefficient * policy_rejected).sum().backward()
        del policy_rejected
        grad_finite = all(p.grad is None or bool(torch.isfinite(p.grad).all()) for p in model.parameters() if p.requires_grad)
        optimizer.step()
        record.update({
            "status": "pass" if grad_finite else "fail_nonfinite_gradient",
            "loss": float(loss.detach()),
            "policy_chosen_logp": float(policy_chosen_value),
            "policy_rejected_logp": float(policy_rejected_value),
            "reference_chosen_logp": float(ref_chosen),
            "reference_rejected_logp": float(ref_rejected),
            "grad_finite": grad_finite,
            "optimizer_step_completed": True,
            "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
            "cuda_peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1048576, 1),
            "cuda_peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 1048576, 1),
            "wall_clock_seconds": time.perf_counter() - started,
        })
    except Exception as exc:
        record.update({
            "status": "fail",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "cuda_peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1048576, 1) if torch.cuda.is_available() else None,
            "cuda_peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 1048576, 1) if torch.cuda.is_available() else None,
            "wall_clock_seconds": time.perf_counter() - started,
        })
    write(record)
    print(json.dumps(record, ensure_ascii=False))
    if record["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
