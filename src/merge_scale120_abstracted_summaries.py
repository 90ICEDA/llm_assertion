from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "outputs" / "scale120_abstracted_summary_inputs"
DEFAULT_OUTPUT_JSON = DEFAULT_INPUT_DIR / "scale120_abstracted_summaries_combined.json"
DEFAULT_CASES_ROOT = ROOT / "rtl_cases_real_scale120"


def case_number(case_id: str) -> int:
    match = re.match(r"case(\d+)_", case_id)
    return int(match.group(1)) if match else 10**9


def load_manifest_case_ids(cases_root: Path) -> list[str]:
    payload = json.loads((cases_root / "case_manifest.json").read_text(encoding="utf-8"))
    return [str(item["name"]) for item in payload.get("cases", [])]


def load_entries(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list in {path}")
    out: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict) and str(item.get("case_id", "")).strip():
            out.append(dict(item))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge per-shard scale120 abstracted summaries into one JSON list.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES_ROOT))
    parser.add_argument("--expect-all-cases", action="store_true", default=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_json = Path(args.output_json).resolve()
    cases_root = Path(args.cases_root).resolve()

    merged: dict[str, dict[str, Any]] = {}
    for path in sorted(input_dir.glob("scale120_abstracted_summaries.shard*-of-*.json")):
        for item in load_entries(path):
            case_id = str(item["case_id"]).strip()
            merged[case_id] = item

    ordered_case_ids = load_manifest_case_ids(cases_root)
    if args.expect_all_cases:
        missing = [case_id for case_id in ordered_case_ids if case_id not in merged]
        if missing:
            raise RuntimeError(
                f"Missing {len(missing)} case summaries before merge completion; first missing cases: {missing[:10]}"
            )

    ordered_rows = [merged[case_id] for case_id in ordered_case_ids if case_id in merged]
    if not ordered_rows:
        ordered_rows = [merged[case_id] for case_id in sorted(merged, key=lambda item: (case_number(item), item))]

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(ordered_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output_json)


if __name__ == "__main__":
    main()
