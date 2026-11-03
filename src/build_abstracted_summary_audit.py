from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"

TRACEABS_DIR = ROOT / "outputs" / THREAD_ID / "trace_abstraction_data"
MULTIMODEL_DIR = ROOT / "outputs" / THREAD_ID / "multi_model_eval_data"
SCALE120_DIR = ROOT / "outputs" / "scale120_full_model_eval_data"
SCALE120_MANIFEST = ROOT / "rtl_cases_real_scale120" / "case_manifest.json"

OUT_DIR = ROOT / "generated_main_results_strict_success"
OUT_CSV = OUT_DIR / "abstracted_summary_audit_20cases.csv"
OUT_JSON = OUT_DIR / "abstracted_summary_root_cause_breakdown.json"

PROMPT_VARIANT = "abstracted_trace_summary"
METHOD_NAME = "spec_rtl_abstracted_trace_summary"
AUDIT_TARGET = 20
MISSING_SAMPLE_COUNT = 12

ASSERTION_RE = re.compile(
    r"assert\s+property\s*\(\s*@\(posedge\s+clk\)\s*disable\s+iff\s*\(!rst_n\)\s*(.*)\)\s*;\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)
EXTRACT_RE = re.compile(r"assert\s+property\s*\([^;]+;\s*", flags=re.IGNORECASE | re.DOTALL)
IDENT_RE = re.compile(r"\$?[A-Za-z_][A-Za-z0-9_$]*")
NUMERIC_RE = re.compile(r"\b\d+'[bdho][0-9a-f_xz?]+\b|\b\d+\b", flags=re.IGNORECASE)

IGNORE_IDENTIFIERS = {
    "assert",
    "property",
    "posedge",
    "disable",
    "iff",
    "clk",
    "rst_n",
    "and",
    "or",
    "not",
    "begin",
    "end",
    "if",
    "else",
    "true",
    "false",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def extract_sva_candidates(response: str) -> list[str]:
    cleaned = response.replace("```systemverilog", "").replace("```", "")
    found: list[str] = []
    for match in EXTRACT_RE.findall(cleaned):
        line = collapse_ws(match).rstrip(";") + ";"
        if line not in found:
            found.append(line)
    if not found:
        for raw_line in cleaned.splitlines():
            line = collapse_ws(raw_line)
            if line.lower().startswith("assert property"):
                if not line.endswith(";"):
                    line += ";"
                if line not in found:
                    found.append(line)
    return found


def assertion_parses(assertion_text: str) -> bool:
    match = ASSERTION_RE.match(assertion_text.strip())
    if not match:
        return False
    body = match.group(1).strip()
    return "|->" in body or "|=>" in body


def parse_allowed_signals(prompt_text: str) -> list[str]:
    match = re.search(r"Allowed signals:\s*(.*?)\n\n\s*Specification:", prompt_text, flags=re.DOTALL)
    if not match:
        return []
    payload = match.group(1).replace("\n", " ")
    return [item.strip() for item in payload.split(",") if item.strip()]


def extract_invalid_identifiers(assertion_text: str, allowed_signals: list[str]) -> list[str]:
    text = NUMERIC_RE.sub(" ", assertion_text)
    allowed = set(allowed_signals)
    allowed_bases = {sig.split("[", 1)[0].strip() for sig in allowed_signals if sig.strip()}
    invalid: list[str] = []
    for token in IDENT_RE.findall(text):
        if token in IGNORE_IDENTIFIERS or token.startswith("$"):
            continue
        base = token.split("[", 1)[0].strip()
        if token in allowed or base in allowed_bases:
            continue
        if token not in invalid:
            invalid.append(token)
    return invalid


def classify_candidate(row: dict[str, str]) -> str:
    if row.get("compile_ok") != "True":
        return "compile_fail"
    if row.get("correct_pass") == "True" and row.get("buggy_fail") == "True":
        return "success"
    if row.get("correct_pass") == "True" and row.get("buggy_fail") != "True":
        if row.get("antecedent_hit") != "True":
            return "vacuity"
        return "too_weak"
    if row.get("correct_pass") != "True" and row.get("buggy_fail") == "True":
        return "too_strong"
    return "ineffective"


def case_number(case_id: str) -> int:
    match = re.match(r"case(\d+)_", case_id)
    return int(match.group(1)) if match else 10**9


def choose_missing_sample(all_case_ids: list[str], legacy_case_ids: set[str]) -> list[str]:
    prim_cases = [
        case_id
        for case_id in sorted(all_case_ids, key=lambda item: (case_number(item), item))
        if case_number(case_id) < 200 and case_id not in legacy_case_ids
    ]
    return prim_cases[:MISSING_SAMPLE_COUNT]


def summarize_prototype_case(
    case_id: str,
    prototype_rows: list[dict[str, str]],
    multimodel_rows: list[dict[str, str]],
    prompt_path: Path,
    full_eval_prompt_exists: bool,
) -> dict[str, Any]:
    prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    allowed_signals = parse_allowed_signals(prompt_text)
    result_rows = [row for row in prototype_rows if row["case_id"] == case_id and row["prompt_variant"] == PROMPT_VARIANT]

    raw_extracted_count = 0
    if result_rows:
        raw_responses = result_rows[0].get("raw_generation_responses", "")
        raw_extracted_count = len(extract_sva_candidates(raw_responses))

    candidate_mode = Counter(classify_candidate(row) for row in result_rows)
    parser_unsupported_count = sum(0 if assertion_parses(row["assertion_text"]) else 1 for row in result_rows)
    invalid_signal_rows = 0
    invalid_signal_idents: list[str] = []
    for row in result_rows:
        extras = extract_invalid_identifiers(row["assertion_text"], allowed_signals)
        if extras:
            invalid_signal_rows += 1
            for item in extras:
                if item not in invalid_signal_idents:
                    invalid_signal_idents.append(item)

    compile_fail_count = candidate_mode.get("compile_fail", 0)
    success_count = candidate_mode.get("success", 0)
    static_filter_false_kill_count = 1 if raw_extracted_count > 0 and not result_rows else 0

    overlapping_multimodel = [
        row
        for row in multimodel_rows
        if row["case_id"] == case_id and row["method"] == METHOD_NAME
    ]
    multimodel_success_count = sum(
        1
        for row in overlapping_multimodel
        if row.get("compile_ok") == "True"
        and row.get("correct_pass") == "True"
        and row.get("buggy_fail") == "True"
    )

    if compile_fail_count == len(result_rows):
        if invalid_signal_rows:
            primary_root_cause = "compile_fail_invalid_or_out_of_scope_identifiers"
        else:
            primary_root_cause = "compile_fail_other"
    elif success_count > 0:
        primary_root_cause = "has_success_not_true_zero"
    elif candidate_mode:
        ranked = sorted(
            ((mode, count) for mode, count in candidate_mode.items() if mode != "success"),
            key=lambda item: (-item[1], item[0]),
        )
        primary_root_cause = ranked[0][0]
        if primary_root_cause == "compile_fail" and invalid_signal_rows:
            primary_root_cause = "compile_fail_invalid_or_out_of_scope_identifiers"
        elif primary_root_cause == "compile_fail":
            primary_root_cause = "compile_fail_other"
    else:
        primary_root_cause = "no_candidates_recorded"

    notes: list[str] = []
    if multimodel_success_count > 0:
        notes.append(f"cross-check rerun later produced {multimodel_success_count} strict-success candidate rows")
    if invalid_signal_idents:
        notes.append("invalid/out-of-scope ids: " + ", ".join(invalid_signal_idents))

    return {
        "case_id": case_id,
        "audit_bucket": "prototype_ran",
        "abstracted_summary_available": True,
        "full_eval_prompt_generated": full_eval_prompt_exists,
        "prototype_prompt_generated": prompt_path.exists(),
        "sva_extracted": bool(result_rows),
        "raw_extracted_candidate_count": raw_extracted_count,
        "recorded_candidate_count": len(result_rows),
        "compile_ok_count": sum(1 for row in result_rows if row.get("compile_ok") == "True"),
        "strict_success_count": success_count,
        "compile_fail_count": compile_fail_count,
        "vacuity_count": candidate_mode.get("vacuity", 0),
        "too_weak_count": candidate_mode.get("too_weak", 0),
        "too_strong_count": candidate_mode.get("too_strong", 0),
        "ineffective_count": candidate_mode.get("ineffective", 0),
        "parser_unsupported_count": parser_unsupported_count,
        "static_filter_false_kill_count": static_filter_false_kill_count,
        "signal_name_missing_count": invalid_signal_rows,
        "signal_name_missing_examples": "; ".join(invalid_signal_idents),
        "primary_root_cause": primary_root_cause,
        "prototype_prompt_path": str(prompt_path.resolve()) if prompt_path.exists() else "",
        "notes": "; ".join(notes),
    }


def summarize_missing_case(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "audit_bucket": "scale120_missing_summary",
        "abstracted_summary_available": False,
        "full_eval_prompt_generated": False,
        "prototype_prompt_generated": False,
        "sva_extracted": False,
        "raw_extracted_candidate_count": 0,
        "recorded_candidate_count": 0,
        "compile_ok_count": 0,
        "strict_success_count": 0,
        "compile_fail_count": 0,
        "vacuity_count": 0,
        "too_weak_count": 0,
        "too_strong_count": 0,
        "ineffective_count": 0,
        "parser_unsupported_count": 0,
        "static_filter_false_kill_count": 0,
        "signal_name_missing_count": 0,
        "signal_name_missing_examples": "",
        "primary_root_cause": "missing_abstracted_summary_not_run",
        "prototype_prompt_path": "",
        "notes": "no abstracted summary entry, so the scale120 full eval never generated this method prompt",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    selected_cases = read_json(TRACEABS_DIR / "selected_cases.json")
    legacy_case_ids = [str(item["case_id"]) for item in selected_cases]
    legacy_case_set = set(legacy_case_ids)

    prototype_rows = read_csv_rows(TRACEABS_DIR / "trace_abstraction_results_raw.csv")
    multimodel_rows = read_csv_rows(MULTIMODEL_DIR / "multi_model_results_raw.csv")
    scale120_rows = read_csv_rows(SCALE120_DIR / "multi_model_results_raw.csv")

    manifest_payload = read_json(SCALE120_MANIFEST)
    all_case_ids = [str(item["name"]) for item in manifest_payload.get("cases", [])]
    missing_sample = choose_missing_sample(all_case_ids, legacy_case_set)

    audit_rows: list[dict[str, Any]] = []
    for case_id in legacy_case_ids:
        prompt_path = TRACEABS_DIR / "prompts" / case_id / "abstracted_trace_summary_prompt.txt"
        full_eval_prompt_exists = any(
            (SCALE120_DIR / "prompts" / model_dir / case_id / f"{METHOD_NAME}.txt").exists()
            for model_dir in ("GPT", "Claude", "Qwen")
        )
        audit_rows.append(
            summarize_prototype_case(
                case_id=case_id,
                prototype_rows=prototype_rows,
                multimodel_rows=multimodel_rows,
                prompt_path=prompt_path,
                full_eval_prompt_exists=full_eval_prompt_exists,
            )
        )

    for case_id in missing_sample:
        audit_rows.append(summarize_missing_case(case_id))

    if len(audit_rows) != AUDIT_TARGET:
        raise RuntimeError(f"Expected {AUDIT_TARGET} audit rows, found {len(audit_rows)}")

    write_csv(OUT_CSV, audit_rows)

    prototype_only = [row for row in audit_rows if row["audit_bucket"] == "prototype_ran"]
    missing_only = [row for row in audit_rows if row["audit_bucket"] == "scale120_missing_summary"]

    prototype_mode_totals = Counter()
    for row in prototype_only:
        prototype_mode_totals["compile_fail"] += int(row["compile_fail_count"])
        prototype_mode_totals["vacuity"] += int(row["vacuity_count"])
        prototype_mode_totals["too_weak"] += int(row["too_weak_count"])
        prototype_mode_totals["too_strong"] += int(row["too_strong_count"])
        prototype_mode_totals["ineffective"] += int(row["ineffective_count"])
        prototype_mode_totals["success"] += int(row["strict_success_count"])

    full_eval_case_ids = sorted({row["case_id"] for row in scale120_rows})
    full_eval_methods = sorted({row["method"] for row in scale120_rows})
    full_eval_abstracted_rows = [row for row in scale120_rows if row["method"] == METHOD_NAME]

    overlapping_multimodel = [
        row for row in multimodel_rows if row["method"] == METHOD_NAME and row["case_id"] in legacy_case_set
    ]
    overlapping_multimodel_success = sum(
        1
        for row in overlapping_multimodel
        if row.get("compile_ok") == "True"
        and row.get("correct_pass") == "True"
        and row.get("buggy_fail") == "True"
    )

    summary = {
        "full_eval_status": {
            "scale120_case_count": len(full_eval_case_ids),
            "scale120_methods_present": full_eval_methods,
            "scale120_abstracted_method_row_count": len(full_eval_abstracted_rows),
            "legacy_abstracted_summary_case_count": len(legacy_case_ids),
            "scale120_cases_without_legacy_abstracted_summary": len(
                [case_id for case_id in full_eval_case_ids if case_id not in legacy_case_set]
            ),
        },
        "audit_sample": {
            "sample_policy": (
                "8 legacy prototype cases with recorded abstracted runs + first 12 non-legacy base prim cases "
                "from the scale120 manifest."
            ),
            "audit_case_count": len(audit_rows),
            "prototype_case_count": len(prototype_only),
            "missing_summary_case_count": len(missing_only),
            "prompt_generated_case_count": sum(1 for row in audit_rows if row["prototype_prompt_generated"]),
            "sva_extracted_case_count": sum(1 for row in audit_rows if row["sva_extracted"]),
            "compile_ok_case_count": sum(1 for row in audit_rows if int(row["compile_ok_count"]) > 0),
            "parser_unsupported_case_count": sum(1 for row in audit_rows if int(row["parser_unsupported_count"]) > 0),
            "static_filter_false_kill_case_count": sum(
                1 for row in audit_rows if int(row["static_filter_false_kill_count"]) > 0
            ),
            "signal_name_missing_case_count": sum(
                1 for row in audit_rows if int(row["signal_name_missing_count"]) > 0
            ),
        },
        "prototype_candidate_breakdown": dict(prototype_mode_totals),
        "case_primary_root_causes": dict(Counter(row["primary_root_cause"] for row in audit_rows)),
        "multimodel_cross_check": {
            "overlap_case_count": len({row["case_id"] for row in overlapping_multimodel}),
            "overlap_candidate_row_count": len(overlapping_multimodel),
            "overlap_strict_success_candidate_rows": overlapping_multimodel_success,
        },
        "limitations": [
            "parser_unsupported_count is inferred from the recorded assertion strings matching the expected assert-property format.",
            "static_filter_false_kill_count is based on recorded prompt/result artifacts; the audited abstracted prototype shows 5 extracted rows for every generated prompt.",
            "compile-fail sub-reasons use recorded assertion text plus allowlist checks; the stored CSV does not include full iverilog stdout for every failed row.",
        ],
        "artifacts": {
            "audit_csv": str(OUT_CSV.resolve()),
            "summary_json": str(OUT_JSON.resolve()),
            "prototype_results": str((TRACEABS_DIR / "trace_abstraction_results_raw.csv").resolve()),
            "scale120_results": str((SCALE120_DIR / "multi_model_results_raw.csv").resolve()),
            "multimodel_results": str((MULTIMODEL_DIR / "multi_model_results_raw.csv").resolve()),
        },
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(OUT_CSV)
    print(OUT_JSON)


if __name__ == "__main__":
    main()
