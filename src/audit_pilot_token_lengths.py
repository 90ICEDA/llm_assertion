from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "outputs/behavioral_preference_pilot_v1"
MANIFEST = PILOT / "behavioral_probes_v3/probe_manifest.json"
MODEL = ROOT / "outputs/checkpoints/Qwen3-8B"
OUT = PILOT / "training_corpora_v2/token_length_audit.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def summary(values: list[int]) -> dict:
    ordered = sorted(values)
    def pct(q: float) -> int:
        return ordered[round((len(ordered) - 1) * q)]
    return {"count": len(values), "min": min(values), "p50": pct(.5), "p90": pct(.9),
            "p95": pct(.95), "p99": pct(.99), "max": max(values),
            "mean": round(statistics.mean(values), 3)}


def main() -> None:
    tokenizer = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = [r for r in manifest["candidate_policy_records"] if r["probe_policy"] == "disagreement_guided"]
    assert len(records) == 240 and len({r["candidate_id"] for r in records}) == 240
    details, prompt_lengths, response_lengths, total_lengths = [], [], [], []
    for r in sorted(records, key=lambda x: x["candidate_id"]):
        prompt_path, response_path = ROOT / r["prompt_path"], ROOT / r["sva_path"]
        p = len(tokenizer.encode(prompt_path.read_text(encoding="utf-8"), add_special_tokens=False).ids)
        s = len(tokenizer.encode(response_path.read_text(encoding="utf-8"), add_special_tokens=False).ids)
        prompt_lengths.append(p); response_lengths.append(s); total_lengths.append(p + s)
        details.append({"candidate_id": r["candidate_id"], "parent_bug_id": r["parent_bug_id"],
                        "prompt_tokens": p, "response_tokens": s, "total_tokens": p + s,
                        "prompt_path": r["prompt_path"], "response_path": r["sva_path"],
                        "prompt_sha256": sha(prompt_path), "response_sha256": sha(response_path)})
    result = {"status": "pass", "tokenizer": str(MODEL.relative_to(ROOT)).replace("\\", "/"),
              "tokenizer_size": tokenizer.get_vocab_size(), "candidate_count": len(details),
              "prompt": summary(prompt_lengths), "response": summary(response_lengths),
              "total": summary(total_lengths), "responses_over_512": sum(x > 512 for x in response_lengths),
              "full_responses_fit_with_one_prompt_token": sum(x + 1 <= 512 for x in response_lengths),
              "details": details}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
