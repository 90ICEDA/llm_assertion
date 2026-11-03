from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "outputs/behavioral_preference_pilot_v1"
QUERY_ROOT = PILOT / "frozen_top1_v1"
MANIFEST = QUERY_ROOT / "query_manifest.json"
OUT = QUERY_ROOT / "generations"
MODEL = ROOT / "outputs/checkpoints/Qwen3-8B"
MANIFEST_SHA256 = "4b57a42c1d06d7ea8a967cd7753ca610368f21698e21564c075a02c4fbafe4ec"
ADAPTERS = {
    "ordinary_sft": ("formal_training_v2/ordinary_sft/checkpoint-008762", "97b28837673e16fab251a0d57aa46eb36efc5e3e0bd215eb2c846330aa8db775"),
    "pass_count_dpo": ("formal_training_v2/pass_count_dpo/checkpoint-004380", "71429e0a6ec962a0fdedcd279600ff73d1a5d2c87f925d0f9f9415c4049fab22"),
    "scalar_score_dpo": ("formal_training_v2/scalar_score_dpo/checkpoint-004380", "0b0fdcce088f88adcbd820f075ed48ddbe98b7ff339421b3839748e53efa28cf"),
    "random_probe_dominance_dpo": ("formal_training_v2/random_probe_dominance_dpo/checkpoint-004371", "81c0225f6b0d8978724b86f97ce8f49e30c9ca59d759d4850bb1a4d9e3661031"),
    "full_disagreement_dominance_dpo": ("formal_training_v2/full_disagreement_dominance_dpo/checkpoint-004373", "8ee63a43f6851f69f6fe3532e61b0fe4bd2ed2c2f948da2a489e42ede6e4f641"),
}
SEED = 20260815


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def dump_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def extract_sva(raw: str) -> str:
    match = re.search(r"assert\s+property\s*\(.*?\)\s*;", raw, flags=re.I | re.S)
    return match.group(0).strip() if match else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true", help="skip immutable completed query outputs")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args()
    if sha(MANIFEST) != MANIFEST_SHA256:
        raise RuntimeError("frozen query manifest hash mismatch")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["status"] != "frozen_before_any_top1_generation" or manifest["query_count"] != 48:
        raise RuntimeError("unexpected query manifest")
    for method, (relative, expected) in ADAPTERS.items():
        adapter = PILOT / relative / "adapter_model.safetensors"
        actual = sha(adapter)
        if actual != expected:
            raise RuntimeError(f"adapter hash mismatch {method}: {actual}")
    if args.preflight_only:
        print(json.dumps({"status": "pass", "query_count": 48, "adapter_count": 5,
                          "generation_count": 240, "manifest_sha256": MANIFEST_SHA256}, sort_keys=True))
        return

    import torch
    import transformers
    from peft import PeftModel, __version__ as peft_version
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    query_rows = sorted(manifest["records"], key=lambda x: x["query_id"])
    token_counts = []
    for row in query_rows:
        prompt = (ROOT / row["prompt_path"]).read_text(encoding="utf-8")
        count = len(tokenizer.encode(prompt, add_special_tokens=False))
        if count + manifest["decode"]["max_new_tokens"] > 40960:
            raise RuntimeError(f"query exceeds context without permitted truncation: {row['case_id']} {count}")
        token_counts.append(count)
    run_manifest = {
        "status": "running", "version": "frozen_top1_generation_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(), "seed": SEED,
        "query_manifest_sha256": MANIFEST_SHA256, "query_count": len(query_rows),
        "adapter_hashes": {k: v[1] for k, v in ADAPTERS.items()},
        "decode": manifest["decode"], "input_token_min": min(token_counts),
        "input_token_max": max(token_counts), "expected_generation_count": 240,
        "command": [sys.executable, *sys.argv], "python": platform.python_version(),
        "torch": torch.__version__, "transformers": transformers.__version__, "peft": peft_version,
        "gpu": torch.cuda.get_device_name(0),
        "once_only_policy": "existing evidence is verified and skipped; never regenerated",
        "extraction_rule": "first regex-matched assert property statement; empty means compile failure; no repair",
    }
    dump_atomic(QUERY_ROOT / "generation_run_manifest.json", run_manifest)
    completed = 0
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
    for method, (relative, adapter_hash) in ADAPTERS.items():
        base = AutoModelForCausalLM.from_pretrained(MODEL, quantization_config=quant, device_map={"": 0},
                                                    local_files_only=True, low_cpu_mem_usage=True)
        model = PeftModel.from_pretrained(base, PILOT / relative, is_trainable=False)
        model.eval()
        for row in query_rows:
            qdir = OUT / method / row["case_id"]
            evidence_path = qdir / "evidence.json"
            if evidence_path.exists():
                old = json.loads(evidence_path.read_text(encoding="utf-8"))
                valid = (old.get("status") == "complete" and old.get("prompt_sha256") == row["prompt_sha256"]
                         and old.get("adapter_sha256") == adapter_hash)
                if args.resume and valid:
                    completed += 1
                    continue
                raise RuntimeError(f"refusing to regenerate existing output: {evidence_path}")
            prompt = (ROOT / row["prompt_path"]).read_text(encoding="utf-8")
            encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
            encoded = {k: v.to("cuda") for k, v in encoded.items()}
            started = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(**encoded, do_sample=False, num_return_sequences=1,
                                           max_new_tokens=512, pad_token_id=tokenizer.pad_token_id,
                                           eos_token_id=tokenizer.eos_token_id, use_cache=True)
            new_ids = generated[0, encoded["input_ids"].shape[1]:].tolist()
            raw = tokenizer.decode(new_ids, skip_special_tokens=True)
            sva = extract_sva(raw)
            qdir.mkdir(parents=True, exist_ok=True)
            raw_path, sva_path = qdir / "raw_response.txt", qdir / "candidate.sva"
            raw_path.write_text(raw, encoding="utf-8", newline="\n")
            sva_path.write_text(sva + ("\n" if sva else ""), encoding="utf-8", newline="\n")
            evidence = {
                "status": "complete", "method": method, "query_id": row["query_id"],
                "case_id": row["case_id"], "memberships": row["memberships"],
                "prompt_path": row["prompt_path"], "prompt_sha256": row["prompt_sha256"],
                "adapter_path": relative, "adapter_sha256": adapter_hash,
                "decode": manifest["decode"], "seed": SEED,
                "input_tokens": int(encoded["input_ids"].shape[1]), "output_tokens": len(new_ids),
                "raw_response_sha256": sha(raw_path), "candidate_sva_sha256": sha(sva_path),
                "sva_extracted": bool(sva), "wall_clock_seconds": time.perf_counter() - started,
                "generated_utc": datetime.now(timezone.utc).isoformat(),
            }
            dump_atomic(evidence_path, evidence)
            completed += 1
        del model, base
        torch.cuda.empty_cache()
    run_manifest.update({"status": "complete", "completed_generation_count": completed,
                         "completed_utc": datetime.now(timezone.utc).isoformat()})
    dump_atomic(QUERY_ROOT / "generation_run_manifest.json", run_manifest)
    print(json.dumps({"status": "complete", "completed_generation_count": completed}, sort_keys=True))


if __name__ == "__main__":
    main()
