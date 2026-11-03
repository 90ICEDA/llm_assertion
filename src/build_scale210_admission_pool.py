from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "rtl_cases_real_scale210_independent"
TARGETS = {"temporal_cross_cycle": 30, "combination_protocol": 20}


def main() -> None:
    with (DATASET / "hardness_admission_report.csv").open(encoding="utf-8-sig", newline="") as handle:
        report = list(csv.DictReader(handle))
    cases = []
    for row in report:
        case_dir = DATASET / row["case_name"]
        metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
        cases.append({
            "case_name": row["case_name"], "parent_bug_id": row["parent_bug_id"],
            "source_project": metadata["source_project"], "source_module": metadata["source_module"],
            "bug_class": row["bug_class"], "decision": row["decision"],
            "golden_gate_ok": row["golden_gate_ok"].lower() == "true",
            "nonvacuous_weak_miss_count": int(row["nonvacuous_weak_miss_count"]),
            "reason": row["reason"],
        })
    admitted = [case for case in cases if case["decision"] == "admitted"]
    rejected = [case for case in cases if case["decision"] == "rejected"]
    counts = Counter(case["bug_class"] for case in admitted)
    deficits = {kind: max(0, target - counts[kind]) for kind, target in TARGETS.items()}
    payload = {
        "schema_version": 1,
        "admission_evidence": "hardness_admission_report.csv evaluator revision 5",
        "targets": TARGETS,
        "admitted_case_count": len(admitted),
        "rejected_case_count": len(rejected),
        "pending_case_count": sum(case["decision"] == "pending" for case in cases),
        "admitted_by_bug_class": dict(counts),
        "deficit_by_bug_class": deficits,
        "replacement_case_count_required": sum(deficits.values()),
        "admitted_project_count": len({case["source_project"] for case in admitted}),
        "admitted_module_count": len({case["source_module"] for case in admitted}),
        "admitted_cases": admitted,
    }
    (DATASET / "formal_admitted_manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (DATASET / "rejected_cases" ).mkdir(exist_ok=True)
    (DATASET / "rejected_cases" / "rejected_case_catalog.json").write_text(
        json.dumps({"schema_version": 1, "case_count": len(rejected), "cases": rejected}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: payload[key] for key in (
        "admitted_case_count", "rejected_case_count", "pending_case_count",
        "admitted_by_bug_class", "deficit_by_bug_class", "replacement_case_count_required",
        "admitted_project_count", "admitted_module_count",
    )}, indent=2))


if __name__ == "__main__":
    main()
