from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from generate_pilot_v2_ast_smoke_v2 import allowed_fn, build_trie, sha

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "outputs/behavioral_preference_pilot_v2"
QUERY_ROOT = V2 / "frozen_top1_ast_v2"
MANIFEST = QUERY_ROOT / "query_manifest.json"
TRAIN = V2 / "formal_training_v3"
ADAPTER_MANIFEST = TRAIN / "final_adapter_manifest.json"
OUT = QUERY_ROOT / "generations"
MODEL = ROOT / "outputs/checkpoints/Qwen3-8B"
SEED = 20260815


def atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    adapters = json.loads(ADAPTER_MANIFEST.read_text(encoding="utf-8"))["methods"]
    if manifest["status"] != "frozen_before_any_top1_generation" or manifest["query_count"] != 48 or len(adapters) != 5:
        raise RuntimeError("unexpected frozen input")
    manifest_hash = sha(MANIFEST)
    for method, record in adapters.items():
        if sha(ROOT / record["adapter_path"] / "adapter_model.safetensors") != record["adapter_sha256"]:
            raise RuntimeError(f"adapter hash mismatch: {method}")
    if args.preflight_only:
        print(json.dumps({"status": "pass", "query_count": 48, "adapter_count": 5, "generation_count": 240,
                          "manifest_sha256": manifest_hash, "adapter_manifest_sha256": sha(ADAPTER_MANIFEST)}, sort_keys=True))
        return

    import torch
    import transformers
    from peft import PeftModel, __version__ as peft_version
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    tokenizer.pad_token_id = tokenizer.eos_token_id
    rows = sorted(manifest["records"], key=lambda x: x["query_id"])
    run = {
        "status": "running", "version": "frozen_top1_ast_v2_generation", "created_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED, "query_manifest_sha256": manifest_hash, "adapter_manifest_sha256": sha(ADAPTER_MANIFEST),
        "expected_generation_count": 240, "decode": manifest["decode"], "command": [sys.executable, *sys.argv],
        "python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__,
        "peft": peft_version, "gpu": torch.cuda.get_device_name(0),
        "once_only_policy": "valid existing evidence is skipped under --resume and never regenerated",
    }
    atomic(QUERY_ROOT / "generation_run_manifest.json", run)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
    completed = 0
    for method, adapter in adapters.items():
        base = AutoModelForCausalLM.from_pretrained(MODEL, quantization_config=quant, device_map={"": 0}, local_files_only=True, low_cpu_mem_usage=True)
        model = PeftModel.from_pretrained(base, ROOT / adapter["adapter_path"], is_trainable=False)
        model.eval()
        for row in rows:
            directory = OUT / method / row["case_id"]
            evidence_path = directory / "evidence.json"
            if evidence_path.exists():
                old = json.loads(evidence_path.read_text(encoding="utf-8"))
                valid = old.get("status") == "complete" and old.get("prompt_sha256") == row["prompt_sha256"] and old.get("adapter_sha256") == adapter["adapter_sha256"]
                if args.resume and valid:
                    completed += 1
                    continue
                raise RuntimeError(f"refusing to regenerate: {evidence_path}")
            prompt = (ROOT / row["prompt_path"]).read_text(encoding="utf-8")
            inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to("cuda")
            prompt_tokens = inputs.input_ids.shape[1]
            trie = build_trie(tokenizer, row["semantic_signals"])
            began = time.perf_counter()
            with torch.inference_mode():
                output = model.generate(**inputs, do_sample=False, num_return_sequences=1, max_new_tokens=128,
                                        eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.eos_token_id,
                                        prefix_allowed_tokens_fn=allowed_fn(trie, prompt_tokens), use_cache=True)
            generated = output[0, prompt_tokens:].tolist()
            ended = bool(generated and generated[-1] == tokenizer.eos_token_id)
            raw = tokenizer.decode(generated[:-1] if ended else generated, skip_special_tokens=False)
            ast = json.loads(raw) if ended else None
            directory.mkdir(parents=True, exist_ok=True)
            raw_path, ast_path = directory / "raw_response.txt", directory / "ast.json"
            raw_path.write_text(raw, encoding="utf-8")
            if ast is not None:
                ast_path.write_text(json.dumps(ast, separators=(",", ":")), encoding="utf-8")
            evidence = {
                "status": "complete", "method": method, "query_id": row["query_id"], "case_id": row["case_id"],
                "memberships": row["memberships"], "prompt_path": row["prompt_path"], "prompt_sha256": row["prompt_sha256"],
                "adapter_path": adapter["adapter_path"], "adapter_sha256": adapter["adapter_sha256"], "decode": manifest["decode"],
                "seed": SEED, "input_tokens": prompt_tokens, "output_tokens_including_eos": len(generated),
                "raw_response_sha256": sha(raw_path), "ast_sha256": sha(ast_path) if ast_path.exists() else None,
                "json_ast_extracted": ast is not None, "schema_keys_valid": isinstance(ast, dict) and tuple(ast) == ("antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation"),
                "ended_on_eos": ended, "hit_max_new_tokens": len(generated) >= 128,
                "generation_constraint": "strict_schema_trie", "wall_clock_seconds": time.perf_counter() - began,
                "generated_utc": datetime.now(timezone.utc).isoformat(),
            }
            atomic(evidence_path, evidence)
            completed += 1
            print(method, row["case_id"], completed, evidence["schema_keys_valid"], ended, flush=True)
        del model, base
        torch.cuda.empty_cache()
    run.update({"status": "complete", "completed_generation_count": completed, "completed_utc": datetime.now(timezone.utc).isoformat()})
    atomic(QUERY_ROOT / "generation_run_manifest.json", run)
    print(json.dumps({"status": "complete", "completed_generation_count": completed}, sort_keys=True))


if __name__ == "__main__":
    main()
