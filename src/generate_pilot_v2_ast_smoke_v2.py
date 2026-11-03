from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "outputs/behavioral_preference_pilot_v2"
DATA = V2 / "training_corpora_v2"
TRAIN = V2 / "formal_training_v3"
OUT = V2 / "ast_smoke_v2"
METHODS = ("ordinary_sft", "pass_count_dpo", "scalar_score_dpo", "random_probe_dominance_dpo", "full_disagreement_dominance_dpo")
PARENTS = ("case510_cc_spill_register_flush_push_priority", "case133_prim_edge_negedge_missing", "case478_axis_srl_register_ready_recovery")
KEYS = ("antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signals_from_prompt(prompt: str) -> list[str]:
    match = re.search(r"must be one of: (.+)\.\n", prompt)
    if not match:
        raise RuntimeError("cannot recover frozen visible-signal set")
    return [item.strip() for item in match.group(1).split(",")]


def valid_objects(signals: list[str]):
    for ant, polarity, cons, implication, relation in itertools.product(
        signals, ("high", "low"), signals, ("|->", "|=>"), ("high", "low", "equal", "not_equal")
    ):
        yield json.dumps(dict(zip(KEYS, (ant, polarity, cons, implication, relation))), separators=(",", ":"))


def build_trie(tokenizer, signals: list[str]) -> dict:
    root = {}
    for text in valid_objects(signals):
        ids = tokenizer.encode(text, add_special_tokens=False)
        node = root
        for token in ids:
            node = node.setdefault(int(token), {})
        node[int(tokenizer.eos_token_id)] = {}
    return root


def allowed_fn(trie: dict, prompt_tokens: int):
    def allowed(_batch_id, input_ids):
        node = trie
        for token in input_ids[prompt_tokens:].tolist():
            node = node.get(int(token))
            if node is None:
                raise RuntimeError("decoder left frozen JSON trie")
        return list(node) if node else []
    return allowed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    adapter_manifest_path = TRAIN / "final_adapter_manifest.json"
    adapter_manifest = json.loads(adapter_manifest_path.read_text(encoding="utf-8"))
    adapters = adapter_manifest["methods"]
    if set(adapters) != set(METHODS):
        raise RuntimeError("adapter manifest method mismatch")
    for method, record in adapters.items():
        adapter = ROOT / record["adapter_path"] / "adapter_model.safetensors"
        if sha(adapter) != record["adapter_sha256"]:
            raise RuntimeError(f"adapter hash mismatch: {method}")
    manifest = {
        "status": "frozen_before_smoke_generation",
        "version": "ast_smoke_v2_strict_trie_eos",
        "parents": list(PARENTS),
        "methods": list(METHODS),
        "slots": 8,
        "generation_count": 120,
        "decode": {"do_sample": False, "temperature": 0.0, "num_return_sequences": 1, "max_new_tokens": 128, "seed": 20260815},
        "constraint": "complete schema-valid canonical JSON trie; exactly five keys; forced EOS immediately after closing brace",
        "adapter_manifest_sha256": sha(adapter_manifest_path),
        "adapters": adapters,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "smoke_manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise RuntimeError("refusing to change frozen ast_smoke_v2 manifest")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.preflight_only:
        print(json.dumps({"status": "pass", "generation_count": 120, "manifest_sha256": sha(manifest_path)}))
        return

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    model_path = ROOT / "outputs/checkpoints/Qwen3-8B"
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
    for method in METHODS:
        base = AutoModelForCausalLM.from_pretrained(model_path, quantization_config=quant, device_map={"": 0}, local_files_only=True, low_cpu_mem_usage=True)
        model = PeftModel.from_pretrained(base, ROOT / adapters[method]["adapter_path"])
        model.eval()
        for parent in PARENTS:
            original = (DATA / "prompts" / parent / "prompt.txt").read_text(encoding="utf-8")
            trie = build_trie(tokenizer, signals_from_prompt(original))
            for slot in range(1, 9):
                directory = OUT / "generations" / method / parent / f"slot_{slot:02d}"
                evidence_path = directory / "evidence.json"
                if args.resume and evidence_path.is_file():
                    continue
                directory.mkdir(parents=True, exist_ok=True)
                prompt = original + f"Smoke diversity slot: {slot}/8. Return one valid object now.\n"
                (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
                inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
                prompt_tokens = inputs.input_ids.shape[1]
                began = time.perf_counter()
                with torch.no_grad():
                    output = model.generate(
                        **inputs,
                        do_sample=False,
                        num_return_sequences=1,
                        max_new_tokens=128,
                        eos_token_id=tokenizer.eos_token_id,
                        pad_token_id=tokenizer.eos_token_id,
                        prefix_allowed_tokens_fn=allowed_fn(trie, prompt_tokens),
                    )
                generated = output[0, prompt_tokens:].tolist()
                ended_on_eos = bool(generated and generated[-1] == tokenizer.eos_token_id)
                raw = tokenizer.decode(generated[:-1] if ended_on_eos else generated, skip_special_tokens=False)
                (directory / "raw_response.txt").write_text(raw, encoding="utf-8")
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    obj = None
                valid = isinstance(obj, dict) and tuple(obj) == KEYS and set(obj) == set(KEYS)
                if valid:
                    (directory / "ast.json").write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
                evidence = {
                    "status": "complete",
                    "method": method,
                    "parent": parent,
                    "slot": slot,
                    "adapter_sha256": adapters[method]["adapter_sha256"],
                    "prompt_sha256": sha(directory / "prompt.txt"),
                    "raw_sha256": sha(directory / "raw_response.txt"),
                    "json_ast_extracted": obj is not None,
                    "schema_keys_valid": valid,
                    "ended_on_eos": ended_on_eos,
                    "output_tokens_including_eos": len(generated),
                    "hit_max_new_tokens": len(generated) >= 128,
                    "generation_constraint": "strict_schema_trie",
                    "wall_clock_seconds": time.perf_counter() - began,
                }
                evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
                print(method, parent, slot, valid, ended_on_eos, flush=True)
        del model, base
        torch.cuda.empty_cache()
    print(json.dumps({"status": "complete", "generation_count": len(list((OUT / "generations").rglob("evidence.json")))}))


if __name__ == "__main__":
    main()
