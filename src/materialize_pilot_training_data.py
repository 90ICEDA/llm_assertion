from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "outputs/behavioral_preference_pilot_v1"
PROBES = PILOT / "behavioral_probes_v3/probe_manifest.json"
FROZEN = PILOT / "training_baseline_definitions_v1_frozen.json"
OUT = PILOT / "training_corpora_v2"
SEED = 20260815
TOKEN_BUDGET = 245_760
POLICY = "disagreement_guided"
FORBIDDEN = ("heldout", "test_result", "test_score", "scs_at_1")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def pair_row(a: dict, b: dict, method: str, score_a: int, score_b: int) -> dict:
    chosen, rejected = (a, b) if score_a > score_b else (b, a)
    hi, lo = max(score_a, score_b), min(score_a, score_b)
    payload = f"{method}\0{chosen['candidate_id']}\0{rejected['candidate_id']}"
    return {
        "pair_id": hashlib.sha256(payload.encode()).hexdigest()[:24],
        "method": method,
        "parent_bug_id": chosen["parent_bug_id"],
        "prompt_path": chosen["prompt_path"],
        "chosen_path": chosen["sva_path"],
        "rejected_path": rejected["sva_path"],
        "chosen_id": chosen["candidate_id"],
        "rejected_id": rejected["candidate_id"],
        "chosen_score": hi,
        "rejected_score": lo,
        "probe_policy": POLICY,
    }


def load_dominance(path: Path, method: str) -> list[dict]:
    rows = []
    for line in read(path).splitlines():
        x = json.loads(line)
        rows.append({
            "pair_id": x["pair_id"], "method": method,
            "parent_bug_id": x["parent_bug_id"],
            "prompt_path": x["chosen_prompt_path"],
            "chosen_path": x["chosen_sva_path"],
            "rejected_path": x["rejected_sva_path"],
            "chosen_id": x["chosen_id"], "rejected_id": x["rejected_id"],
            "probe_policy": x["probe_policy"],
        })
    return sorted(rows, key=lambda r: r["pair_id"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()
    definitions = json.loads(read(FROZEN))
    assert definitions["pass_count_dpo"]["integer_formula"] == "pass_count(c) = (32 - |FP_c|) + |TP_c|"
    assert definitions["scalar_score_dpo"]["integer_formula"] == "raw_score(c) = |TP_c| - 2*|FP_c|"
    manifest = json.loads(read(PROBES))
    records = [r for r in manifest["candidate_policy_records"] if r["probe_policy"] == POLICY]
    assert len(records) == 240 and len({r["candidate_id"] for r in records}) == 240
    assert all(r["query_budget"] == 32 for r in records)
    for r in records:
        lowered = json.dumps(r, sort_keys=True).lower()
        assert not any(key in lowered for key in FORBIDDEN)
        for key in ("prompt_path", "sva_path"):
            path = ROOT / r[key]
            assert path.is_file(), path
    by_parent: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_parent[r["parent_bug_id"]].append(r)
    assert len(by_parent) == 30 and all(len(v) == 8 for v in by_parent.values())

    sft = [{
        "example_id": r["candidate_id"], "method": "ordinary_sft",
        "parent_bug_id": r["parent_bug_id"], "prompt_path": r["prompt_path"],
        "response_path": r["sva_path"],
        "label_source": "all_executable_candidates_without_behavioral_selection",
    } for r in sorted(records, key=lambda x: x["candidate_id"])]
    pass_pairs, scalar_pairs = [], []
    for parent in sorted(by_parent):
        candidates = sorted(by_parent[parent], key=lambda x: x["candidate_id"])
        for i, a in enumerate(candidates):
            for b in candidates[i + 1:]:
                pa = 32 - len(a["fp_probe_ids"]) + len(a["tp_mutant_ids"])
                pb = 32 - len(b["fp_probe_ids"]) + len(b["tp_mutant_ids"])
                if pa != pb:
                    pass_pairs.append(pair_row(a, b, "pass_count_dpo", pa, pb))
                sa = len(a["tp_mutant_ids"]) - 2 * len(a["fp_probe_ids"])
                sb = len(b["tp_mutant_ids"]) - 2 * len(b["fp_probe_ids"])
                if sa != sb:
                    scalar_pairs.append(pair_row(a, b, "scalar_score_dpo", sa, sb))

    corpora = {
        "ordinary_sft.jsonl": sft,
        "pass_count_dpo.jsonl": sorted(pass_pairs, key=lambda r: r["pair_id"]),
        "scalar_score_dpo.jsonl": sorted(scalar_pairs, key=lambda r: r["pair_id"]),
        "random_probe_dominance_dpo.jsonl": load_dominance(PILOT / "dominance_pairs_v3/random_legal_dominance_pairs.jsonl", "random_probe_dominance_dpo"),
        "full_disagreement_dominance_dpo.jsonl": load_dominance(PILOT / "dominance_pairs_v3/disagreement_guided_dominance_pairs.jsonl", "full_disagreement_dominance_dpo"),
    }
    assert len(corpora["full_disagreement_dominance_dpo.jsonl"]) >= 300
    if args.check_only:
        print(json.dumps({k: len(v) for k, v in corpora.items()}, sort_keys=True))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in corpora.items():
        write_jsonl(OUT / name, rows)
    frozen_training = {
        "status": "frozen_before_formal_training",
        "version": "pilot_training_v2_full_response",
        "seed": SEED,
        "model": "outputs/checkpoints/Qwen3-8B",
        "loss_token_budget_per_method": TOKEN_BUDGET,
        "budget_epoch_count": 1,
        "max_sequence_tokens": 512,
        "sequence_policy": "keep full response; truncate prompt from the left only if prompt+response exceeds 512",
        "padding_policy": "batch_size_1_no_padding; attention mask covers exactly real tokens",
        "loss_token_accounting": "SFT=response non-padding tokens; DPO=chosen plus rejected response non-padding tokens",
        "token_repetition": "forbidden",
        "ordinary_sft_definition": "all 240 executable candidates; no FP/TP/probe/held-out selection",
        "shared_qlora": {"bits": 4, "quant": "nf4", "double_quant": True, "lora_r": 8,
                         "lora_alpha": 16, "lora_dropout": 0.05, "targets": ["q_proj", "v_proj"]},
        "optimizer": {"name": "AdamW", "lr": 0.0001, "beta": 0.1},
        "source_hashes": {"probe_manifest": sha(PROBES), "baseline_definitions": sha(FROZEN)},
    }
    (OUT / "formal_training_v2_frozen.json").write_text(json.dumps(frozen_training, indent=2) + "\n", encoding="utf-8")
    audit = {"status": "pass", "forbidden_fields": list(FORBIDDEN), "counts": {k: len(v) for k, v in corpora.items()},
             "parent_counts": {k: len({r["parent_bug_id"] for r in v}) for k, v in corpora.items()}}
    (OUT / "materialization_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    hashes = {p.name: sha(p) for p in sorted(OUT.glob("*")) if p.is_file()}
    (OUT / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, sort_keys=True))


if __name__ == "__main__":
    main()
