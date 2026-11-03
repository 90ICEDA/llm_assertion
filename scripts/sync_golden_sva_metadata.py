from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "rtl_cases_real_scale210_independent"


def main() -> None:
    changed = []
    for case_dir in sorted(ROOT.glob("case4*")):
        path = case_dir / "golden.sva"
        metadata_path = case_dir / "case_metadata.json"
        if not path.is_file() or not metadata_path.is_file():
            continue
        match = re.search(r"assert\s+property\s*\([\s\S]*?\)\s*;", path.read_text(encoding="utf-8"))
        if not match:
            continue
        assertion = " ".join(match.group(0).split())
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        value = metadata.get("golden_sva")
        if isinstance(value, dict):
            key = "assertion" if "assertion" in value else "sva"
            if value.get(key) == assertion:
                continue
            value[key] = assertion
        elif value == assertion:
            continue
        else:
            metadata["golden_sva"] = assertion
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed.append(case_dir.name)
    print(json.dumps({"changed_count": len(changed), "changed_cases": changed}, indent=2))


if __name__ == "__main__":
    main()
