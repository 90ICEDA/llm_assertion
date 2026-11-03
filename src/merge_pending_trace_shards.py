from __future__ import annotations

import argparse
import csv
from pathlib import Path


KEYS = ("model_label", "case_id", "method", "candidate_index")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    merged = {}
    for path in sorted(Path(args.shards_root).glob("shard_*/pending_candidates.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                merged[tuple(row[key] for key in KEYS)] = row
    rows = list(merged.values())
    if not rows: raise RuntimeError("No pending candidates found")
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(f"merged_candidates={len(rows)} cases={len({x['case_id'] for x in rows})} -> {output}")


if __name__ == "__main__": main()
