#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from decoy_structure import ensure_decoy_structure


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill explicit overfit-decoy artifacts and metadata for every case in a dataset root."
    )
    parser.add_argument("--root", required=True, help="Dataset root containing case_manifest.json.")
    parser.add_argument(
        "--output-csv",
        help="Optional CSV report describing the decoy backfill status.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    rows = ensure_decoy_structure(root)
    if args.output_csv:
        out_csv = Path(args.output_csv).resolve()
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(rows[0].keys()) if rows else []
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        print(f"[DONE] Wrote decoy structure report: {out_csv}")

    passed = sum(1 for row in rows if row["decoy_structure_ok"])
    print(f"SUMMARY: {passed}/{len(rows)} cases now have explicit decoy structure.")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
