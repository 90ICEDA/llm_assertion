from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def parent_id(case_id: str) -> str:
    match = re.search(r"_from_(case\d+_.+)$", case_id)
    return match.group(1) if match else case_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))["cases"]
    parents = set(policy[f"{args.split}_parent_ids"])
    cases = sorted(row["name"] for row in manifest if parent_id(row["name"]) in parents)
    shards = [cases[index::args.shards] for index in range(args.shards)]
    payload = {"split": args.split, "parent_ids": sorted(parents), "case_ids": cases, "shards": shards}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"split": args.split, "parents": len(parents), "cases": len(cases), "shards": [len(x) for x in shards]}))


if __name__ == "__main__": main()
