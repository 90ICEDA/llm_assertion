#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "outputs/final46_main_experiment/run"
METHOD = "spec_rtl_raw_trace"
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def filter_csv(path: Path) -> tuple[int, int]:
    if not path.is_file():
        return 0, 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    kept = [row for row in rows if row.get("method") != METHOD]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(kept)
    return len(rows), len(kept)


def main() -> None:
    for model in ("GPT", "Claude", "Qwen"):
        trace = RUN / model / "trace"
        for name in ("multi_model_results_raw.csv", "multi_model_prompt_log.csv"):
            before, after = filter_csv(trace / name)
            print(f"{model} {name}: {before} -> {after}")


if __name__ == "__main__":
    main()
