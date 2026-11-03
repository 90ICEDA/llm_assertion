#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases_root", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260719)
    args = parser.parse_args()
    cases = json.loads((args.cases_root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]
    # Sample one canonical case per independent parent before random selection,
    # so trace variants cannot crowd out module/bug diversity.
    canonical = {}
    for case in cases:
        parent = str(case.get("parent_bug_id") or case.get("seed_case_name") or case["name"])
        current = canonical.get(parent)
        if current is None or str(case["name"]) == parent:
            canonical[parent] = str(case["name"])
    population = sorted(canonical.values())
    if len(population) < args.count:
        raise ValueError(f"Only {len(population)} independent parents available")
    sample = sorted(random.Random(args.seed).sample(population, args.count))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps({"seed": args.seed, "cases": sample}, indent=2) + "\n", encoding="utf-8")
    print("\n".join(sample))


if __name__ == "__main__":
    main()
