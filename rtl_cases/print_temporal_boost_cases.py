#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the 40 new scale160 temporal-boost case names."
    )
    parser.add_argument(
        "--summary-json",
        default="D:/AssertionForge-main1/rtl_cases_real_scale160_temporal_boosted/temporal_variant_expansion_summary.json",
        help="Path to temporal_variant_expansion_summary.json.",
    )
    parser.add_argument(
        "--format",
        choices=["plain", "bash_args", "powershell_args"],
        default="plain",
        help="Output format.",
    )
    args = parser.parse_args()

    summary_path = Path(args.summary_json).resolve()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    case_names = [str(name) for name in payload.get("new_case_names", [])]

    if args.format == "plain":
        for name in case_names:
            print(name)
        return 0

    if args.format == "bash_args":
        print(" ".join(f'--case "{name}"' for name in case_names))
        return 0

    print(" ".join(f'--case \\"{name}\\"' for name in case_names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
