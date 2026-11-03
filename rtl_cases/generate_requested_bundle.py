#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


def to_bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_manifest_cases(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def summarize_method_rows(rows: List[Dict[str, str]]) -> Dict[str, int]:
    case_names = {row["case_name"] for row in rows if row.get("case_name")}
    return {
        "rows": len(rows),
        "cases": len(case_names),
        "compile_ok_rows": sum(1 for row in rows if to_bool(row.get("compile_ok"))),
        "strict_success_rows": sum(1 for row in rows if to_bool(row.get("strict_success"))),
        "trace_overfit_rows": sum(1 for row in rows if to_bool(row.get("trace_overfit"))),
    }


def classify_trace_summary_miss(rows: List[Dict[str, str]]) -> str:
    if all(int(row.get("buggy_antecedent_hits", "0") or "0") == 0 for row in rows):
        return "根本没触发"
    if any(
        to_bool(row.get("non_vacuous")) and not to_bool(row.get("pass_on_correct"))
        for row in rows
    ):
        return "时序算子错"
    if any(
        to_bool(row.get("pass_on_correct"))
        and to_bool(row.get("non_vacuous"))
        and not to_bool(row.get("fail_on_buggy"))
        for row in rows
    ):
        return "consequent 太保守"
    return "antecedent 太弱"


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_root = repo_root / "docs" / "real_rtl_scaleout"
    active_root = repo_root / "rtl_cases_real_active"
    admitted_root = repo_root / "rtl_cases_real_admitted_20260619"

    manifest_cases = load_manifest_cases(active_root)
    manifest_by_name = {str(case["name"]): case for case in manifest_cases}

    main_table = read_csv(admitted_root / "strict_eval_case_dedup_by_method_and_bug_class_iv12.csv")
    gap_table = read_csv(admitted_root / "strict_eval_case_dedup_gap_vs_spec_plus_rtl_iv12.csv")
    dedup_rows = read_csv(admitted_root / "strict_eval_case_dedup_rows_iv12.csv")
    strict_rows = read_csv(admitted_root / "strict_eval_report_iv12.csv")
    golden_rows = read_csv(active_root / "golden_sva_check_report.csv")

    golden_out = docs_root / "golden_self_check_active_30cases.csv"
    write_csv(
        golden_out,
        [
            "case_name",
            "compile_ok",
            "pass_on_correct",
            "fail_on_buggy",
            "non_vacuous",
            "antecedent_triggered",
            "buggy_antecedent_hits",
            "golden_ok",
            "failure_reason",
        ],
        golden_rows,
    )

    overfit_summary_rows: List[Dict[str, object]] = []
    strict_grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in strict_rows:
        strict_grouped[str(row.get("method", ""))].append(row)

    dedup_grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in dedup_rows:
        dedup_grouped[str(row.get("method", ""))].append(row)

    for method in sorted(strict_grouped):
        s = summarize_method_rows(strict_grouped[method])
        dedup_method_rows = dedup_grouped.get(method, [])
        strict_success_cases = sum(1 for row in dedup_method_rows if to_bool(row.get("strict_success")))
        trace_overfit_cases = sum(
            1
            for row in dedup_method_rows
            if "trace_overfit" in str(row.get("failure_types_seen", "")).split(";")
        )
        overfit_summary_rows.append(
            {
                "method": method,
                "row_count": s["rows"],
                "case_count": s["cases"],
                "strict_success_rows": s["strict_success_rows"],
                "strict_success_cases": strict_success_cases,
                "trace_overfit_rows": s["trace_overfit_rows"],
                "trace_overfit_cases": trace_overfit_cases,
            }
        )

    overfit_summary_out = docs_root / "overfit_generalization_summary_iv12.csv"
    write_csv(
        overfit_summary_out,
        [
            "method",
            "row_count",
            "case_count",
            "strict_success_rows",
            "strict_success_cases",
            "trace_overfit_rows",
            "trace_overfit_cases",
        ],
        overfit_summary_rows,
    )

    overfit_detail_rows: List[Dict[str, object]] = []
    for row in strict_rows:
        if not to_bool(row.get("trace_overfit")):
            continue
        case = manifest_by_name.get(str(row.get("case_name", "")), {})
        overfit_detail_rows.append(
            {
                "case_name": row.get("case_name", ""),
                "method": row.get("method", ""),
                "candidate_index": row.get("candidate_index", ""),
                "bug_class": case.get("bug_class", ""),
                "source_module": case.get("source_module", ""),
                "overfit_lure_present": bool(str(case.get("overfit_lure", "")).strip()),
                "overfit_lure": case.get("overfit_lure", ""),
                "trace_overfit_reason": row.get("trace_overfit_reason", ""),
                "assertion_line": row.get("assertion_line", ""),
            }
        )

    overfit_detail_out = docs_root / "trace_overfit_detail_iv12.csv"
    write_csv(
        overfit_detail_out,
        [
            "case_name",
            "method",
            "candidate_index",
            "bug_class",
            "source_module",
            "overfit_lure_present",
            "overfit_lure",
            "trace_overfit_reason",
            "assertion_line",
        ],
        overfit_detail_rows,
    )

    trace_summary_rows = [row for row in strict_rows if str(row.get("method", "")) == "spec_rtl_trace_summary"]
    ts_grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in trace_summary_rows:
        ts_grouped[str(row.get("case_name", ""))].append(row)

    dedup_trace_summary = {
        row["case_name"]: row
        for row in dedup_rows
        if str(row.get("method", "")) == "spec_rtl_trace_summary"
    }

    miss_rows: List[Dict[str, object]] = []
    for case_name, row in sorted(dedup_trace_summary.items()):
        if to_bool(row.get("buggy_fail")):
            continue
        candidates = ts_grouped.get(case_name, [])
        case = manifest_by_name.get(case_name, {})
        miss_rows.append(
            {
                "case_name": case_name,
                "bug_class": case.get("bug_class", ""),
                "source_module": case.get("source_module", ""),
                "overfit_lure_present": bool(str(case.get("overfit_lure", "")).strip()),
                "primary_attribution": classify_trace_summary_miss(candidates),
                "raw_failure_types_seen": row.get("failure_types_seen", ""),
                "row_count": row.get("row_count", ""),
                "any_compile_ok": row.get("compile_ok", ""),
                "any_correct_pass": row.get("correct_pass", ""),
                "any_buggy_fail": row.get("buggy_fail", ""),
                "any_non_vacuous": row.get("non_vacuous", ""),
                "max_buggy_antecedent_hits": max(
                    (int(r.get("buggy_antecedent_hits", "0") or "0") for r in candidates),
                    default=0,
                ),
                "candidate_indices": row.get("candidate_indices", ""),
            }
        )

    miss_out = docs_root / "trace_summary_miss_attribution_full_iv12.csv"
    write_csv(
        miss_out,
        [
            "case_name",
            "bug_class",
            "source_module",
            "overfit_lure_present",
            "primary_attribution",
            "raw_failure_types_seen",
            "row_count",
            "any_compile_ok",
            "any_correct_pass",
            "any_buggy_fail",
            "any_non_vacuous",
            "max_buggy_antecedent_hits",
            "candidate_indices",
        ],
        miss_rows,
    )

    report_path = docs_root / "requested_bundle_report_20260621.md"
    gap_lookup = {row["bug_class"]: row for row in gap_table}
    combo_gap = gap_lookup.get("combination_same_cycle", {})
    temp_gap = gap_lookup.get("temporal_cross_cycle", {})
    overall_gap = gap_lookup.get("overall", {})

    overfit_case_names = sorted({str(row["case_name"]) for row in overfit_detail_rows})
    lure_overfit_case_names = sorted(
        {
            str(row["case_name"])
            for row in overfit_detail_rows
            if str(row.get("overfit_lure_present", "")).lower() == "true"
        }
    )

    lines = [
        "# Requested Bundle (2026-06-21)",
        "",
        "## 1. Main Table",
        "",
        f"- Case-dedup main table: `{admitted_root / 'strict_eval_case_dedup_by_method_and_bug_class_iv12.csv'}`",
        f"- Gap table: `{admitted_root / 'strict_eval_case_dedup_gap_vs_spec_plus_rtl_iv12.csv'}`",
        f"- combination_same_cycle gap: correct_pass {combo_gap.get('gap_vs_spec_plus_rtl_correct_pass', '')}, fail_on_buggy {combo_gap.get('gap_vs_spec_plus_rtl_buggy_fail', '')}, strict_success {combo_gap.get('gap_vs_spec_plus_rtl_strict_success', '')}",
        f"- temporal_cross_cycle gap: correct_pass {temp_gap.get('gap_vs_spec_plus_rtl_correct_pass', '')}, fail_on_buggy {temp_gap.get('gap_vs_spec_plus_rtl_buggy_fail', '')}, strict_success {temp_gap.get('gap_vs_spec_plus_rtl_strict_success', '')}",
        f"- overall gap: correct_pass {overall_gap.get('gap_vs_spec_plus_rtl_correct_pass', '')}, fail_on_buggy {overall_gap.get('gap_vs_spec_plus_rtl_buggy_fail', '')}, strict_success {overall_gap.get('gap_vs_spec_plus_rtl_strict_success', '')}",
        "",
        "## 2. Dataset",
        "",
        f"- Manifest and inventory: `{docs_root / 'dataset_inventory_30cases.csv'}`",
        f"- Source manifest: `{active_root / 'case_manifest.json'}`",
        "",
        "## 3. Golden Self-Check",
        "",
        f"- Golden report: `{golden_out}`",
        "- Result: 30/30 pass.",
        "",
        "## 4. Antecedent Coverage",
        "",
        f"- Antecedent report: `{docs_root / 'antecedent_coverage_30cases.csv'}`",
        "- Result: 30/30 have buggy antecedent hits > 0.",
        "",
        "## 5. Overfit / Generalization",
        "",
        f"- Summary: `{overfit_summary_out}`",
        f"- Detail: `{overfit_detail_out}`",
        f"- Trace overfit cases: {', '.join(overfit_case_names) if overfit_case_names else 'none'}",
        f"- Trace overfit lure cases: {', '.join(lure_overfit_case_names) if lure_overfit_case_names else 'none'}",
        "",
        "## 6. Trace Summary Miss Attribution",
        "",
        f"- Full attribution table: `{miss_out}`",
        "",
        "## 7. Judgment",
        "",
        "- The scaled-up case-dedup result does not show a robust breakout where trace summary clearly wins over spec+RTL on a bug class.",
        "- Combination cases improve correct_pass a bit (+2) but lose fail_on_buggy (-1).",
        "- Temporal cases improve fail_on_buggy (+4) but lose correct_pass (-1).",
        "- strict_success stays 0, so there is still no evidence of a stable end-to-end advantage.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[DONE] Wrote golden self-check copy: {golden_out}")
    print(f"[DONE] Wrote overfit summary: {overfit_summary_out}")
    print(f"[DONE] Wrote overfit detail: {overfit_detail_out}")
    print(f"[DONE] Wrote trace-summary miss attribution: {miss_out}")
    print(f"[DONE] Wrote bundle report: {report_path}")


if __name__ == "__main__":
    main()
