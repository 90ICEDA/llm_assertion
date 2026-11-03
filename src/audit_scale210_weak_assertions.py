from __future__ import annotations

import csv
import json
from pathlib import Path
import argparse
import re


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "rtl_cases_real_scale210_independent"
REQUIRED_KINDS = {
    "single_cycle_implication",
    "final_output_only",
    "delay_removed",
    "antecedent_removed",
    "simple_invariant",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DATASET)
    args = parser.parse_args()
    dataset = args.root.resolve()
    rows = []
    for case_dir in sorted(
        p for p in dataset.iterdir() if p.is_dir() and re.match(r"^case\d+_", p.name)
    ):
        errors = []
        path = case_dir / "weak_assertions.json"
        assertions = []
        if not path.is_file():
            errors.append("missing weak_assertions.json")
        else:
            doc = json.loads(path.read_text(encoding="utf-8"))
            assertions = doc.get("assertions", doc.get("candidates", doc if isinstance(doc, list) else []))
            if not isinstance(assertions, list):
                assertions = []
                errors.append("assertions is not a list")
        kinds = {
            item.get("kind") or item.get("weakness_class") or item.get("weakening_type")
            for item in assertions if isinstance(item, dict)
        }
        missing = sorted(REQUIRED_KINDS - kinds)
        if missing:
            errors.append("missing kinds:" + ",".join(missing))
        if len(assertions) < 5:
            errors.append("fewer than five weak assertions")
        names = []
        for index, item in enumerate(assertions):
            if not isinstance(item, dict):
                errors.append(f"assertion[{index}] is not an object")
                continue
            name = item.get("name") or item.get("id")
            names.append(name)
            if not name:
                errors.append(f"assertion[{index}] missing name")
            if not (item.get("sva") or item.get("assertion") or item.get("expression") or item.get("property")):
                errors.append(f"assertion[{index}] missing SVA")
            if "nonempty_antecedent" not in item and "antecedent_nonempty" not in item:
                errors.append(f"assertion[{index}] missing nonempty_antecedent")
            if not (item.get("rationale") or item.get("expected_weakness")):
                errors.append(f"assertion[{index}] missing rationale")
        if len(names) != len(set(names)):
            errors.append("duplicate assertion names")
        sva_path = case_dir / "weak_assertions.sva"
        if not sva_path.is_file() or sva_path.stat().st_size == 0:
            errors.append("missing/empty weak_assertions.sva")
        rows.append({
            "case_name": case_dir.name,
            "assertion_count": len(assertions),
            "required_kind_count": len(REQUIRED_KINDS & kinds),
            "schema_ok": not errors,
            "errors": ";".join(errors),
        })

    if not rows:
        raise SystemExit(f"no case<number>_* directories found under {dataset}")
    out = dataset / "weak_assertion_schema_audit.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "case_count": len(rows),
        "schema_pass_count": sum(bool(row["schema_ok"]) for row in rows),
        "schema_fail_count": sum(not bool(row["schema_ok"]) for row in rows),
        "all_schema_ok": all(bool(row["schema_ok"]) for row in rows),
        "semantic_status": "pending WSL execution; schema pass is not hardness admission",
    }
    (dataset / "weak_assertion_schema_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["all_schema_ok"] else 1)


if __name__ == "__main__":
    main()
