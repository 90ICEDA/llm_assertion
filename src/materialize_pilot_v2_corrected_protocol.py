from __future__ import annotations

import json
from pathlib import Path

import materialize_pilot_v2_ast_training as original

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "outputs/behavioral_preference_pilot_v2"
OLD = V2 / "training_corpora_v1"
NEW = V2 / "training_corpora_v2"
METHODS = original.METHODS
KEYS = ("antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation")


def sha(path: Path) -> str:
    return original.sha(path)


def compact_ast(path: Path) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))
    if set(value) != set(KEYS):
        raise RuntimeError(f"non-canonical AST schema: {path}")
    return json.dumps({key: value[key] for key in KEYS}, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    if (NEW / "materialization_audit.json").exists():
        raise RuntimeError(f"refusing to overwrite existing corrected corpus: {NEW}")
    NEW.mkdir(parents=True, exist_ok=True)
    prompt_map = {}
    for path in sorted((OLD / "prompts").rglob("prompt.txt")):
        parent = path.parent.name
        body = path.read_text(encoding="utf-8")
        body = body.replace(
            "Return exactly one compact JSON object and no prose or SystemVerilog.\n",
            "Return exactly one compact JSON object, then EOS. Output no prose, markdown, metadata, or SystemVerilog.\n",
        )
        body += "The object must contain exactly the five declared keys; extra keys are invalid.\n"
        dest = NEW / "prompts" / parent / "prompt.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        prompt_map[parent] = str(dest.relative_to(ROOT)).replace("\\", "/")

    response_map = {}
    for path in sorted((OLD / "responses").glob("*.json")):
        text = compact_ast(path)
        dest = NEW / "responses" / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        response_map[path.name] = str(dest.relative_to(ROOT)).replace("\\", "/")

    counts = {}
    for method in METHODS:
        rows = original.readl(OLD / f"{method}.jsonl")
        for row in rows:
            row["prompt_path"] = prompt_map[row["parent_bug_id"]]
            for field in ("response_path", "chosen_path", "rejected_path"):
                if field in row:
                    row[field] = response_map[Path(row[field]).name]
        out = NEW / f"{method}.jsonl"
        out.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        counts[method] = len(rows)

    old_frozen = json.loads((OLD / "formal_training_v2_frozen.json").read_text(encoding="utf-8"))
    frozen = {
        **old_frozen,
        "status": "frozen_before_pilot_v2_corrected_training",
        "version": "pilot_v2_corrected_json_ast_eos_v1",
        "response_eos_required": True,
        "response_serialization": "canonical compact JSON; exactly five ordered keys; no trailing newline; EOS supervised as final loss token",
        "inference_constraint": "token trie over complete schema-valid objects; closing brace followed by forced EOS",
        "formal_training_directory": "formal_training_v3",
    }
    frozen_path = NEW / "formal_training_v2_frozen.json"
    frozen_path.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")

    audit = {
        "status": "pass",
        "parents": len(prompt_map),
        "responses": len(response_map),
        "corpora": counts,
        "strict_five_keys": True,
        "canonical_compact_json": True,
        "response_eos_supervised": True,
        "v1_written": False,
        "ast_smoke_v1_written": False,
    }
    (NEW / "materialization_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in sorted(NEW.rglob("*")) if p.is_file()}
    (NEW / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, sort_keys=True))


if __name__ == "__main__":
    main()
