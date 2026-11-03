from __future__ import annotations

import json
import time
from pathlib import Path

import bitsandbytes
import datasets
import peft
import torch
import transformers
import trl
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "outputs/checkpoints/Qwen3-8B"
OUT = ROOT / "outputs/behavioral_preference_pilot_v1/training_environment_smoke.json"


def main() -> None:
    torch.manual_seed(20260815)
    started = time.perf_counter()
    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL,
        quantization_config=quant,
        device_map={"": 0},
        local_files_only=True,
        low_cpu_mem_usage=True,
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.config.use_cache = False
    config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, config)
    text = "Generate one SystemVerilog assertion for this RTL behavior: request implies response on the next cycle."
    encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=64)
    encoded = {key: value.to("cuda") for key, value in encoded.items()}
    labels = encoded["input_ids"].clone()
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=1e-4)
    before = {name: p.detach().float().cpu().clone() for name, p in model.named_parameters() if p.requires_grad}
    output = model(**encoded, labels=labels)
    loss = output.loss
    loss.backward()
    grad_finite = all(p.grad is None or bool(torch.isfinite(p.grad).all()) for p in model.parameters() if p.requires_grad)
    optimizer.step()
    changed = any(not torch.equal(before[name], p.detach().float().cpu()) for name, p in model.named_parameters() if p.requires_grad)
    record = {
        "status": "pass" if grad_finite and changed else "fail",
        "seed": 20260815,
        "model_path": str(MODEL.relative_to(ROOT)).replace("\\", "/"),
        "versions": {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "transformers": transformers.__version__,
            "trl": trl.__version__,
            "peft": peft.__version__,
            "datasets": datasets.__version__,
            "bitsandbytes": bitsandbytes.__version__,
        },
        "gpu": torch.cuda.get_device_name(0),
        "quantization": {"bits": 4, "type": "nf4", "double_quant": True, "compute_dtype": "float16"},
        "lora": {"r": 16, "alpha": 32, "dropout": 0.05, "target_modules": sorted(config.target_modules)},
        "sequence_tokens": int(encoded["input_ids"].numel()),
        "loss": float(loss.detach()),
        "grad_finite": grad_finite,
        "optimizer_changed_trainable_parameter": changed,
        "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
        "total_parameters_reported": sum(p.numel() for p in model.parameters()),
        "cuda_allocated_peak_mib": round(torch.cuda.max_memory_allocated() / 1048576, 1),
        "cuda_reserved_peak_mib": round(torch.cuda.max_memory_reserved() / 1048576, 1),
        "wall_clock_seconds": time.perf_counter() - started,
    }
    OUT.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    if record["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
