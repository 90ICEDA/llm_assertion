from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/dev_locked_score_reranker/selected_candidates.csv"
OUT = ROOT / "outputs/failure_guided_missing4/selected_candidates_missing4.csv"
MANIFEST = ROOT / "outputs/failure_guided_missing4/construction_manifest.json"


def remove_disable_iff(text: str) -> str:
    return re.sub(r"\s*disable\s+iff\s*\([^)]*\)", "", text, count=1, flags=re.I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(SOURCE))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    source, out = Path(args.source).resolve(), Path(args.out).resolve()
    df = pd.read_csv(source, encoding="utf-8-sig")

    # Use four different cases so every repair is an independent one-call target.
    specs = [
        ("compile_fail", "GPT", "assert property (@(posedge clk) disable iff (!rst_n) (1'b1) |-> );"),
        # A legal SystemVerilog final immediate assertion, deliberately outside
        # the evaluator's supported concurrent-property grammar.
        ("unsupported", "Claude", "assert final (1'b1);"),
        ("signal_missing", "GPT", "assert property (@(posedge clk) disable iff (!rst_n) ghost_signal |-> 1'b1);"),
        ("reset_misuse", "Claude", None),
    ]
    used: set[str] = set()
    rows, records = [], []
    for category, model, assertion in specs:
        eligible = df[(df.model_label == model) & ~df.case_id.isin(used)]
        row = eligible.iloc[0].copy()
        used.add(str(row.case_id))
        if category == "reset_misuse":
            assertion = remove_disable_iff(str(row.assertion_text))
        row["assertion_text"] = assertion

        # These flags describe the deliberately constructed original candidate.
        # Overlapping diagnoses are intentional and are retained in the report.
        row["compile_ok"] = category != "compile_fail" and category != "signal_missing"
        row["parser_support"] = category != "unsupported" and category != "reset_misuse"
        row["signal_exists"] = category != "signal_missing"
        row["reset_usage"] = category != "reset_misuse"
        # Do not infer semantic failures when compilation/static checking stops
        # evaluation. Keeping these dimensions true makes the intended missing
        # diagnosis (plus unavoidable parser/reset overlap) explicit.
        row["seen_good_pass"] = True
        row["seen_bad_fail"] = True
        row["seen_antecedent_hit"] = True
        row["non_vacuous"] = True
        row["literal_hardcoding"] = False
        row["heldout_correct_pass"] = False
        row["heldout_buggy_fail"] = False
        row["heldout_antecedent_hit"] = False
        row["heldout_non_vacuous"] = False
        row["trace_overfit"] = False
        rows.append(row)
        records.append({
            "primary_missing_category": category,
            "model": model,
            "case_id": str(row.case_id),
            "parent_bug_id": str(row.parent_bug_id),
            "constructed_assertion": assertion,
            "expected_overlap_note": "compile failure may overlap unsupported or missing-signal diagnosis",
        })

    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
    manifest = {
        "schema_version": 1,
        "purpose": "Empirical one-step repair coverage for the four previously empty diagnosis categories",
        "candidate_count": 4,
        "required_categories": [x[0] for x in specs],
        "one_repair_call_per_candidate": True,
        "does_not_modify_original_repair_freeze": True,
        "candidates": records,
    }
    (out.parent / "construction_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(out)
    print(out.parent / "construction_manifest.json")


if __name__ == "__main__":
    main()
