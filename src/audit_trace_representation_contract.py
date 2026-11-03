from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from trace_representation_contract import (
    TRACE_REPRESENTATIONS,
    case_contract_inputs,
    validate_temporal_relation_abstraction,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the fixed four trace representations and temporal abstraction contract.")
    parser.add_argument("--root", default=str(ROOT / "rtl_cases_real_scale120"))
    parser.add_argument(
        "--summaries",
        default=str(ROOT / "outputs" / "scale120_abstracted_summary_inputs" / "scale120_abstracted_summaries_combined.json"),
    )
    parser.add_argument("--output-dir", default=str(ROOT / "outputs" / "trace_representation_contract_audit"))
    parser.add_argument("--allow-failures", action="store_true")
    args = parser.parse_args()

    cases_root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((cases_root / "case_manifest.json").read_text(encoding="utf-8"))
    meta_by_case = {item["name"]: item for item in manifest.get("cases", [])}
    summaries = json.loads(Path(args.summaries).resolve().read_text(encoding="utf-8"))

    rows = []
    for item in summaries:
        case_id = str(item.get("case_id", "")).strip()
        errors = validate_temporal_relation_abstraction(
            str(item.get("abstracted_summary", "")),
            **case_contract_inputs(cases_root / case_id, meta_by_case.get(case_id, {})),
        )
        rows.append({
            "case_id": case_id,
            "pass": not errors,
            "errors": ";".join(errors),
            "representations": ",".join(TRACE_REPRESENTATIONS),
        })

    csv_path = output_dir / "trace_representation_contract_audit.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["case_id", "pass", "errors", "representations"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "fixed_representations": list(TRACE_REPRESENTATIONS),
        "audited_cases": len(rows),
        "pass_cases": sum(bool(row["pass"]) for row in rows),
        "fail_cases": sum(not bool(row["pass"]) for row in rows),
        "all_pass": all(bool(row["pass"]) for row in rows),
    }
    summary_path = output_dir / "trace_representation_contract_audit_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(csv_path)
    if rows and not summary["all_pass"] and not args.allow_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
