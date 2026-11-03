#!/usr/bin/env python3
from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "outputs/final46_mechanism_controls"
STAMP = "20260808_pre_repair"
VALID_MODELS = {"GPT", "Claude", "Qwen"}


def valid_row(name: str, row: dict[str, str]) -> bool:
    if row.get("model_label", "") not in VALID_MODELS:
        return False
    if not row.get("case_id", "").startswith("case"):
        return False
    if not row.get("method", "").startswith("spec_rtl_"):
        return False
    if name in {"multi_model_results_raw.csv", "pending_candidates.csv"}:
        try:
            return int(float(row.get("candidate_index", ""))) in {1, 2, 3, 4}
        except ValueError:
            return False
    return True


def key_for(name: str, row: dict[str, str]) -> tuple[str, ...]:
    base = (row["model_label"], row["case_id"], row["method"])
    if name in {"multi_model_results_raw.csv", "pending_candidates.csv"}:
        return (*base, str(int(float(row["candidate_index"]))))
    return base


def repair(path: Path) -> dict[str, int | str]:
    backup = path.with_name(path.name + f".{STAMP}.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        physical = list(reader)
    valid: list[dict[str, str]] = []
    malformed = 0
    for values in physical:
        if len(values) != len(header):
            malformed += 1
            continue
        row = dict(zip(header, values))
        if valid_row(path.name, row):
            valid.append(row)
        else:
            malformed += 1
    by_key: dict[tuple[str, ...], dict[str, str]] = {}
    for row in valid:
        by_key[key_for(path.name, row)] = row
    tmp = path.with_suffix(path.suffix + ".repairing")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(by_key.values())
    tmp.replace(path)
    return {
        "path": str(path), "physical_rows": len(physical), "kept_rows": len(by_key),
        "malformed_or_illegal": malformed, "duplicate_keys_removed": len(valid) - len(by_key),
    }


def main() -> None:
    names = {"multi_model_results_raw.csv", "multi_model_prompt_log.csv", "pending_candidates.csv"}
    for path in sorted(ROOT.glob("*/*/*.csv")):
        if path.name in names:
            print(repair(path))


if __name__ == "__main__":
    main()
