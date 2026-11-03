from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "outputs/behavioral_preference_pilot_v1"
DATA = PILOT / "training_corpora_v2"
FORMAL_TRAINING_DIR = "formal_training_v2"
METHODS = {
    "ordinary_sft": "ordinary_sft.jsonl",
    "pass_count_dpo": "pass_count_dpo.jsonl",
    "scalar_score_dpo": "scalar_score_dpo.jsonl",
    "random_probe_dominance_dpo": "random_probe_dominance_dpo.jsonl",
    "full_disagreement_dominance_dpo": "full_disagreement_dominance_dpo.jsonl",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def token_ids(tokenizer, text: str) -> list[int]:
    encoded = tokenizer.encode(text, add_special_tokens=False)
    return encoded.ids if hasattr(encoded, "ids") else encoded


def sequence_parts(tokenizer, prompt: str, response: str) -> tuple[list[int], list[int]]:
    p, r = token_ids(tokenizer, prompt), token_ids(tokenizer, response)
    # Newer frozen protocols may require EOS to be a supervised response token.
    # The default remains false so archived v1/v2 runs retain their exact behavior.
    frozen_path = DATA / "formal_training_v2_frozen.json"
    require_eos = frozen_path.is_file() and json.loads(frozen_path.read_text(encoding="utf-8")).get("response_eos_required", False)
    if require_eos:
        eos = getattr(tokenizer, "eos_token_id", None)
        if eos is None and hasattr(tokenizer, "token_to_id"):
            eos = tokenizer.token_to_id("<|im_end|>")
        if eos is None:
            raise ValueError("frozen protocol requires EOS but tokenizer has no EOS id")
        if not r or r[-1] != eos:
            r.append(eos)
    if not p or not r:
        raise ValueError("prompt and response must both contain real tokens")
    if len(r) > 512:
        raise ValueError(f"full response does not fit frozen 512-token maximum: {len(r)}")
    p = p[-(512 - len(r)):] if len(p) + len(r) > 512 else p
    return p, r


def tensor(tokenizer, prompt: str, response: str) -> tuple[torch.Tensor, int]:
    p, r = sequence_parts(tokenizer, prompt, response)
    return torch.tensor([p + r], dtype=torch.long, device="cuda"), len(p)


def response_logp(model, ids: torch.Tensor, response_start: int) -> torch.Tensor:
    out = model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False)
    logits = out.logits[:, :-1, :]
    labels = ids[:, 1:]
    logps = F.log_softmax(logits.float(), dim=-1).gather(-1, labels.unsqueeze(-1)).squeeze(-1)
    value = logps[:, response_start - 1:].sum(-1)
    del out, logits, labels, logps
    return value


def exact_budget_schedule(costs: list[int], budget: int, seed: int) -> list[int]:
    if not costs or min(costs) <= 0:
        raise ValueError("all loss-token costs must be positive")
    order = list(range(len(costs)))
    random.Random(seed).shuffle(order)
    reserve = min(5000, budget)
    schedule, total, cursor = [], 0, 0
    while total + costs[order[cursor % len(order)]] <= budget - reserve:
        idx = order[cursor % len(order)]
        schedule.append(idx); total += costs[idx]; cursor += 1
    remainder = budget - total
    first_for_cost = {}
    for idx in order:
        first_for_cost.setdefault(costs[idx], idx)
    previous: list[tuple[int, int] | None] = [None] * (remainder + 1)
    previous[0] = (-1, -1)
    for value in range(remainder + 1):
        if previous[value] is None:
            continue
        for cost, idx in first_for_cost.items():
            nxt = value + cost
            if nxt <= remainder and previous[nxt] is None:
                previous[nxt] = (value, idx)
    if previous[remainder] is None:
        raise ValueError(f"cannot exactly materialize loss-token budget {budget}; remainder={remainder}")
    tail, value = [], remainder
    while value:
        value, idx = previous[value]
        tail.append(idx)
    schedule.extend(reversed(tail))
    assert sum(costs[i] for i in schedule) == budget
    return schedule


def save(model, optimizer, out: Path, step: int, metadata: dict) -> None:
    ckpt = out / f"checkpoint-{step:06d}"
    ckpt.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(ckpt, safe_serialization=True)
    torch.save(optimizer.state_dict(), ckpt / "optimizer.pt")
    (ckpt / "state.json").write_text(json.dumps({**metadata, "completed_steps": step}, indent=2) + "\n", encoding="utf-8")
    (out / "latest_checkpoint.txt").write_text(ckpt.name + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True, choices=METHODS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--save-steps", type=int, default=500)
    args = ap.parse_args()
    frozen_path = DATA / "formal_training_v2_frozen.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    corpus = DATA / METHODS[args.method]
    examples = rows(corpus)
    is_sft = args.method == "ordinary_sft"
    assert examples and frozen["seed"] == 20260815
    from tokenizers import Tokenizer
    audit_tokenizer = Tokenizer.from_file(str(ROOT / frozen["model"] / "tokenizer.json"))
    costs, sequence_lengths, prompt_truncations = [], [], 0
    for row in examples:
        if is_sft:
            response_paths = [row["response_path"]]
        else:
            response_paths = [row["chosen_path"], row["rejected_path"]]
        prompt_text = (ROOT / row["prompt_path"]).read_text(encoding="utf-8")
        response_cost = 0
        original_prompt_tokens = len(token_ids(audit_tokenizer, prompt_text))
        for p in response_paths:
            response_text = (ROOT / p).read_text(encoding="utf-8")
            prompt_ids, response_ids = sequence_parts(audit_tokenizer, prompt_text, response_text)
            response_cost += len(response_ids)
            sequence_lengths.append(len(prompt_ids) + len(response_ids))
            prompt_truncations += int(len(prompt_ids) < original_prompt_tokens)
        costs.append(response_cost)
    schedule = exact_budget_schedule(costs, frozen["loss_token_budget_per_method"], frozen["seed"])
    steps = len(schedule)
    out = PILOT / FORMAL_TRAINING_DIR / args.method
    metadata = {"method": args.method, "seed": frozen["seed"], "steps": steps,
                "loss_token_budget": sum(costs[i] for i in schedule),
                "min_loss_tokens_per_step": min(costs), "max_loss_tokens_per_step": max(costs),
                "token_repetition": False, "full_response_preserved": True,
                "max_sequence_tokens_observed": max(sequence_lengths),
                "prompt_truncation_count": prompt_truncations,
                "padding_policy": "batch_size_1; no padding; exact all-ones attention mask",
                "response_eos_required": bool(frozen.get("response_eos_required", False)),
                "corpus": str(corpus.relative_to(ROOT)).replace("\\", "/"), "corpus_sha256": sha(corpus),
                "frozen_config_sha256": sha(frozen_path)}
    if args.dry_run:
        print(json.dumps({**metadata, "records": len(examples), "status": "dry_run_pass"}, sort_keys=True))
        return
    global torch, F, LoraConfig, PeftModel, get_peft_model
    global AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    import torch
    import torch.nn.functional as F
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(frozen["seed"])
    random.seed(frozen["seed"])
    model_path = ROOT / frozen["model"]
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                              bnb_4bit_compute_dtype=torch.float16)
    base = AutoModelForCausalLM.from_pretrained(model_path, quantization_config=quant, device_map={"": 0},
                                                local_files_only=True, low_cpu_mem_usage=True)
    base.gradient_checkpointing_enable()
    base.enable_input_require_grads()
    base.config.use_cache = False
    start = 0
    resume_dir = None
    if args.resume and (out / "latest_checkpoint.txt").is_file():
        resume_dir = out / (out / "latest_checkpoint.txt").read_text().strip()
        model = PeftModel.from_pretrained(base, resume_dir, is_trainable=True)
        start = json.loads((resume_dir / "state.json").read_text())["completed_steps"]
    else:
        cfg = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                         target_modules=["q_proj", "v_proj"])
        model = get_peft_model(base, cfg)
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=1e-4)
    if resume_dir is not None:
        optimizer.load_state_dict(torch.load(resume_dir / "optimizer.pt", map_location="cpu", weights_only=True))
    log_path = out / "train_log.jsonl"
    began = time.perf_counter()
    for step in range(start, steps):
        row = examples[schedule[step]]
        prompt = (ROOT / row["prompt_path"]).read_text(encoding="utf-8")
        optimizer.zero_grad(set_to_none=True)
        if is_sft:
            response = (ROOT / row["response_path"]).read_text(encoding="utf-8")
            ids, response_start = tensor(tokenizer, prompt, response)
            response_tokens = ids.shape[1] - response_start
            logp = response_logp(model, ids, response_start)
            loss = -logp.mean() / response_tokens
            loss.backward()
        else:
            chosen, chosen_start = tensor(tokenizer, prompt, (ROOT / row["chosen_path"]).read_text(encoding="utf-8"))
            rejected, rejected_start = tensor(tokenizer, prompt, (ROOT / row["rejected_path"]).read_text(encoding="utf-8"))
            with torch.no_grad(), model.disable_adapter():
                rc = response_logp(model, chosen, chosen_start).detach()
                rr = response_logp(model, rejected, rejected_start).detach()
            torch.cuda.empty_cache()
            with torch.no_grad():
                pc = response_logp(model, chosen, chosen_start).detach()
                pr = response_logp(model, rejected, rejected_start).detach()
                margin = (pc - pr) - (rc - rr)
                loss = -F.logsigmoid(0.1 * margin).mean()
                coefficient = -0.1 * torch.sigmoid(-0.1 * margin)
            torch.cuda.empty_cache()
            (coefficient * response_logp(model, chosen, chosen_start)).sum().backward()
            torch.cuda.empty_cache()
            (-coefficient * response_logp(model, rejected, rejected_start)).sum().backward()
        finite = all(p.grad is None or bool(torch.isfinite(p.grad).all()) for p in model.parameters() if p.requires_grad)
        if not finite:
            raise FloatingPointError(f"non-finite gradient at step {step + 1}")
        torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad), 1.0)
        optimizer.step()
        record = {"step": step + 1, "loss": float(loss.detach()), "record_id": row.get("pair_id", row.get("example_id")),
                  "loss_tokens": costs[schedule[step]], "elapsed_seconds": time.perf_counter() - began,
                  "cuda_peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1048576, 1)}
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        if (step + 1) % args.save_steps == 0 or step + 1 == steps:
            save(model, optimizer, out, step + 1, metadata)
    result = {**metadata, "status": "pass", "completed_steps": steps,
              "wall_clock_seconds": time.perf_counter() - began,
              "cuda_peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1048576, 1),
              "cuda_peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 1048576, 1)}
    (out / "training_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
