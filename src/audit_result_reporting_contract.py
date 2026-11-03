#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from unified_result_reporting import CONFIDENCE_COLUMNS, OVERLAP_VALUES, REQUIRED_OUTPUT_COLUMNS, SCOPES, UNITS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--final", action="store_true", help="Reject unknown overlap status")
    args = parser.parse_args()
    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    errors = []
    missing = [col for col in REQUIRED_OUTPUT_COLUMNS if col not in df.columns]
    if missing:
        errors.append(f"missing columns: {missing}")
    if not missing:
        scopes = set(df["selection_scope"])
        units = set(df["aggregation_unit"])
        if scopes != set(SCOPES):
            errors.append(f"selection scopes={sorted(scopes)}, expected={list(SCOPES)}")
        if units != set(UNITS):
            errors.append(f"aggregation units={sorted(units)}, expected={list(UNITS)}")
        invalid_overlap = sorted(set(df["overlap_status"]) - set(OVERLAP_VALUES))
        if invalid_overlap:
            errors.append(f"invalid overlap statuses: {invalid_overlap}")
        if args.final and (df["overlap_status"] == "unknown").any():
            errors.append("final table contains overlap_status=unknown")
        if args.final:
            missing_confidence = [col for col in CONFIDENCE_COLUMNS if col not in df.columns]
            if missing_confidence:
                errors.append(f"final table missing confidence columns: {missing_confidence}")
            else:
                if not (pd.to_numeric(df["ci_level"], errors="coerce") == 0.95).all():
                    errors.append("final table must use 95% confidence intervals")
                if not (df["bootstrap_unit"] == "parent_bug_id").all():
                    errors.append("final table bootstrap_unit must be parent_bug_id")
        for col in ["model", "method", "sample_definition", "dedup_key", "parent_aggregation"]:
            if df[col].isna().any() or (df[col].astype(str).str.strip() == "").any():
                errors.append(f"blank required values in {col}")
        if (pd.to_numeric(df["case_count"], errors="coerce") <= 0).any():
            errors.append("case_count must be positive")
        if (pd.to_numeric(df["parent_bug_count"], errors="coerce") <= 0).any():
            errors.append("parent_bug_count must be positive")
    result = {"path": str(args.csv), "row_count": len(df), "contract_ok": not errors, "errors": errors}
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
