from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RTL_CASES_DIR = ROOT / "rtl_cases"
if str(RTL_CASES_DIR) not in sys.path:
    sys.path.insert(0, str(RTL_CASES_DIR))

from sva_eval_grammar import extract_single_assertion  # type: ignore  # noqa: E402


DEFAULT_INPUT_CSV = ROOT / "outputs" / "scale120_full_model_eval_data" / "multi_model_results_raw.csv"
DEFAULT_OUT_DIR = ROOT / "generated_main_results_strict_success"
SUMMARY_CSV = "traceguard_rerank_summary.csv"
CELL_MATRIX_CSV = "traceguard_rerank_cell_matrix.csv"
SELECTED_CSV = "traceguard_rerank_selected_candidates.csv"
README_MD = "traceguard_rerank_readme.md"
SUMMARY_JSON = "traceguard_rerank_summary.json"

CELL_KEYS = ["model_label", "provider", "model_name", "method", "case_id"]
POLICY_ORDER = ["baseline_first", "best_of_k_oracle", "traceguard_rerank"]
METHOD_ORDER = [
    "ALL",
    "spec_only",
    "spec_plus_rtl",
    "spec_rtl_raw_trace",
    "spec_rtl_trace_summary",
    "spec_rtl_abstracted_trace_summary",
]


def parse_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    lowered = series.fillna("").astype(str).str.strip().str.lower()
    return lowered.isin(["true", "1", "yes"])


def parse_int_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def parser_supported(assertion_text: str) -> bool:
    try:
        extract_single_assertion(str(assertion_text or "").strip())
        return True
    except Exception:
        return False


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    bool_cols = [
        "compile_ok",
        "correct_pass",
        "buggy_fail",
        "antecedent_hit_buggy",
        "non_vacuous_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
        "heldout_non_vacuous",
        "trace_overfit",
        "literal_hardcoding",
        "semantic_reasonable",
    ]
    for col in bool_cols:
        if col in out.columns:
            out[col] = parse_bool_series(out[col])
        else:
            out[col] = False

    if "candidate_index" in out.columns:
        out["candidate_index"] = parse_int_series(out["candidate_index"])
    else:
        out["candidate_index"] = 0

    if "seen_bad_ant_hits" in out.columns:
        out["seen_bad_ant_hits"] = parse_int_series(out["seen_bad_ant_hits"])
    else:
        out["seen_bad_ant_hits"] = 0

    out["parser_supported"] = out["assertion_text"].fillna("").astype(str).apply(parser_supported)
    out["seen_antecedent_hit"] = out["antecedent_hit_buggy"] | (out["seen_bad_ant_hits"] > 0)
    out["seen_non_vacuous"] = out["non_vacuous_buggy"] | (out["seen_bad_ant_hits"] > 0)
    out["heldout_detect_bug"] = (
        out["heldout_buggy_fail"] & out["heldout_antecedent_hit"] & out["heldout_non_vacuous"]
    )
    out["heldout_success"] = out["heldout_correct_pass"] & out["heldout_buggy_fail"]
    out["strict_success"] = out["heldout_correct_pass"] & out["heldout_detect_bug"]
    out["mdr_event"] = ~out["heldout_detect_bug"]
    out["fpr_event"] = ~out["heldout_correct_pass"]
    return out


def traceguard_gate_failures(row: pd.Series) -> list[str]:
    failures: list[str] = []
    gate_checks = [
        ("compile_pass", bool(row["compile_ok"])),
        ("correct_pass", bool(row["correct_pass"])),
        ("buggy_fail", bool(row["buggy_fail"])),
        ("non_vacuous_seen", bool(row["seen_non_vacuous"])),
        ("seen_antecedent_hit", bool(row["seen_antecedent_hit"])),
        ("no_hard_coded_literal", not bool(row["literal_hardcoding"])),
        ("no_unsupported_syntax", bool(row["parser_supported"])),
    ]
    for name, ok in gate_checks:
        if not ok:
            failures.append(name)
    return failures


def pick_baseline(sub: pd.DataFrame) -> tuple[pd.Series, str]:
    chosen = sub.sort_values(["candidate_index", "assertion_text"]).iloc[0]
    return chosen, "first_candidate"


def pick_best_of_k(sub: pd.DataFrame) -> tuple[pd.Series, str]:
    ranked = sub.sort_values(
        [
            "strict_success",
            "heldout_success",
            "heldout_detect_bug",
            "heldout_correct_pass",
            "candidate_index",
        ],
        ascending=[False, False, False, False, True],
    )
    chosen = ranked.iloc[0]
    return chosen, "oracle_heldout_rank"


def pick_traceguard(sub: pd.DataFrame) -> tuple[pd.Series, str, int]:
    passing_mask = sub.apply(lambda row: len(traceguard_gate_failures(row)) == 0, axis=1)
    passing = sub.loc[passing_mask].sort_values(["candidate_index", "assertion_text"])
    if not passing.empty:
        return passing.iloc[0], "filtered_first", int(len(passing))
    fallback, _ = pick_baseline(sub)
    return fallback, "baseline_fallback", 0


def build_selected_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, sub in df.groupby(CELL_KEYS, dropna=False, sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_map = {col: val for col, val in zip(CELL_KEYS, keys)}
        sub = sub.sort_values(["candidate_index", "assertion_text"]).reset_index(drop=True)
        baseline_row, baseline_source = pick_baseline(sub)
        best_row, best_source = pick_best_of_k(sub)
        traceguard_row, traceguard_source, passing_count = pick_traceguard(sub)

        policy_rows = [
            ("baseline_first", baseline_row, baseline_source, int(len(sub))),
            ("best_of_k_oracle", best_row, best_source, int(len(sub))),
            ("traceguard_rerank", traceguard_row, traceguard_source, passing_count),
        ]
        for policy_name, chosen, selection_source, passing_candidates in policy_rows:
            gate_failures = traceguard_gate_failures(chosen)
            row = {
                **key_map,
                "selection_policy": policy_name,
                "selection_source": selection_source,
                "available_candidate_count": int(len(sub)),
                "traceguard_passing_candidate_count": int(passing_candidates),
                "selected_candidate_index": int(chosen["candidate_index"]),
                "selected_assertion_text": str(chosen["assertion_text"]),
                "compile_ok": bool(chosen["compile_ok"]),
                "correct_pass": bool(chosen["correct_pass"]),
                "buggy_fail": bool(chosen["buggy_fail"]),
                "seen_antecedent_hit": bool(chosen["seen_antecedent_hit"]),
                "seen_non_vacuous": bool(chosen["seen_non_vacuous"]),
                "heldout_correct_pass": bool(chosen["heldout_correct_pass"]),
                "heldout_buggy_fail": bool(chosen["heldout_buggy_fail"]),
                "heldout_antecedent_hit": bool(chosen["heldout_antecedent_hit"]),
                "heldout_non_vacuous": bool(chosen["heldout_non_vacuous"]),
                "heldout_detect_bug": bool(chosen["heldout_detect_bug"]),
                "heldout_success": bool(chosen["heldout_success"]),
                "strict_success": bool(chosen["strict_success"]),
                "mdr_event": bool(chosen["mdr_event"]),
                "fpr_event": bool(chosen["fpr_event"]),
                "trace_overfit": bool(chosen["trace_overfit"]),
                "literal_hardcoding": bool(chosen["literal_hardcoding"]),
                "parser_supported": bool(chosen["parser_supported"]),
                "semantic_reasonable": bool(chosen["semantic_reasonable"]),
                "failure_mode": str(chosen.get("failure_mode", "")),
                "failure_reason": str(chosen.get("failure_reason", "")),
                "traceguard_gate_failures": ";".join(gate_failures),
            }
            rows.append(row)
    return pd.DataFrame(rows)


def summarize(selected_df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, sub in selected_df.groupby(group_cols, dropna=False, sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {col: val for col, val in zip(group_cols, keys)}
        total = int(len(sub))
        row.update(
            {
                "selected_cell_count": total,
                "case_count": int(sub["case_id"].nunique()),
                "strict_success_count": int(sub["strict_success"].sum()),
                "strict_success_rate": float(sub["strict_success"].mean()) if total else 0.0,
                "heldout_success_count": int(sub["heldout_success"].sum()),
                "heldout_success_rate": float(sub["heldout_success"].mean()) if total else 0.0,
                "detect_bug_count": int(sub["heldout_detect_bug"].sum()),
                "detect_bug_rate": float(sub["heldout_detect_bug"].mean()) if total else 0.0,
                "MDR_count": int(sub["mdr_event"].sum()),
                "MDR": float(sub["mdr_event"].mean()) if total else 0.0,
                "FPR_count": int(sub["fpr_event"].sum()),
                "FPR": float(sub["fpr_event"].mean()) if total else 0.0,
                "trace_overfit_count": int(sub["trace_overfit"].sum()),
                "trace_overfit_rate": float(sub["trace_overfit"].mean()) if total else 0.0,
                "literal_hardcoding_count": int(sub["literal_hardcoding"].sum()),
                "literal_hardcoding_rate": float(sub["literal_hardcoding"].mean()) if total else 0.0,
                "parser_supported_rate": float(sub["parser_supported"].mean()) if total else 0.0,
            }
        )
        if "selection_source" in sub.columns:
            row["baseline_fallback_count"] = int((sub["selection_source"] == "baseline_fallback").sum())
            row["filtered_first_count"] = int((sub["selection_source"] == "filtered_first").sum())
        rows.append(row)
    return pd.DataFrame(rows)


def build_cell_matrix(selected_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, sub in selected_df.groupby(CELL_KEYS, dropna=False, sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {col: val for col, val in zip(CELL_KEYS, keys)}
        row["candidate_count"] = int(sub["available_candidate_count"].max())
        row["traceguard_passing_candidate_count"] = int(sub["traceguard_passing_candidate_count"].max())
        for policy in POLICY_ORDER:
            policy_sub = sub.loc[sub["selection_policy"] == policy]
            if policy_sub.empty:
                continue
            picked = policy_sub.iloc[0]
            prefix = policy
            row[f"{prefix}_candidate_index"] = int(picked["selected_candidate_index"])
            row[f"{prefix}_selection_source"] = str(picked["selection_source"])
            row[f"{prefix}_strict_success"] = bool(picked["strict_success"])
            row[f"{prefix}_heldout_success"] = bool(picked["heldout_success"])
            row[f"{prefix}_MDR"] = bool(picked["mdr_event"])
            row[f"{prefix}_FPR"] = bool(picked["fpr_event"])
            row[f"{prefix}_trace_overfit"] = bool(picked["trace_overfit"])
            row[f"{prefix}_literal_hardcoding"] = bool(picked["literal_hardcoding"])
            row[f"{prefix}_parser_supported"] = bool(picked["parser_supported"])
            row[f"{prefix}_failure_mode"] = str(picked["failure_mode"])
            row[f"{prefix}_traceguard_gate_failures"] = str(picked["traceguard_gate_failures"])
        rows.append(row)
    return pd.DataFrame(rows)


def build_summary_json(summary_df: pd.DataFrame, input_csv: Path) -> dict[str, object]:
    overall_df = summary_df.loc[summary_df["model_label"] == "ALL"].copy()
    payload: dict[str, object] = {
        "input_csv": str(input_csv),
        "selection_policy_order": POLICY_ORDER,
        "cell_definition": CELL_KEYS,
        "strict_success_definition": "heldout_correct_pass && heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous",
        "heldout_success_definition": "heldout_correct_pass && heldout_buggy_fail",
        "detect_bug_definition": "heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous",
        "traceguard_filter_definition": [
            "compile_pass",
            "correct_pass",
            "buggy_fail",
            "non_vacuous_seen",
            "seen_antecedent_hit",
            "no_hard_coded_literal",
            "no_unsupported_syntax",
        ],
    }
    for policy in POLICY_ORDER:
        policy_rows = overall_df.loc[overall_df["selection_policy"] == policy].copy()
        per_method = {}
        for _, row in policy_rows.sort_values("method").iterrows():
            per_method[str(row["method"])] = {
                "strict_success_rate": float(row["strict_success_rate"]),
                "MDR": float(row["MDR"]),
                "FPR": float(row["FPR"]),
                "heldout_success_rate": float(row["heldout_success_rate"]),
                "trace_overfit_rate": float(row["trace_overfit_rate"]),
            }
        payload[policy] = per_method
    return payload


def build_readme() -> str:
    return "\n".join(
        [
            "# TraceGuard Rerank Summary",
            "",
            "- Cell definition: `(model_label, provider, model_name, method, case_id)`.",
            "- `baseline_first`: select the smallest `candidate_index` in each cell.",
            "- `best_of_k_oracle`: held-out oracle upper bound; rank by `strict_success`, then `heldout_success`, then `detect_bug`, then `heldout_correct_pass`, then smaller `candidate_index`.",
            "- `traceguard_rerank`: filter on seen-side/static gates only, then pick the smallest surviving `candidate_index`; if none survive, fall back to `baseline_first`.",
            "- TraceGuard gates:",
            "  - `compile_pass`",
            "  - `correct_pass`",
            "  - `buggy_fail`",
            "  - `non_vacuous_seen`",
            "  - `seen_antecedent_hit`",
            "  - `no_hard_coded_literal`",
            "  - `no_unsupported_syntax`",
            "- Held-out fields are never used by `traceguard_rerank` selection. They are used only for final evaluation and for the `best_of_k_oracle` upper bound.",
            "- `heldout_success = heldout_correct_pass && heldout_buggy_fail`.",
            "- `strict_success = heldout_correct_pass && heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous`.",
            "- `MDR = 1 - detect_bug_rate`, where `detect_bug = heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous`.",
            "- `FPR = 1 - heldout_correct_pass_rate`.",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build minimal TraceGuard rerank artifacts from existing candidate results.")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT_CSV), help="Path to multi_model_results_raw.csv")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory")
    args = parser.parse_args()

    input_csv = Path(args.input_csv).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_df = pd.read_csv(input_csv, encoding="utf-8-sig")
    raw_df = add_derived_columns(raw_df)
    selected_df = build_selected_rows(raw_df)
    selected_df["selection_policy"] = pd.Categorical(selected_df["selection_policy"], POLICY_ORDER, ordered=True)
    selected_df["method"] = pd.Categorical(selected_df["method"], METHOD_ORDER, ordered=True)
    selected_df = selected_df.sort_values(["selection_policy", "model_label", "method", "case_id"]).reset_index(drop=True)
    selected_df["selection_policy"] = selected_df["selection_policy"].astype(str)
    selected_df["method"] = selected_df["method"].astype(str)

    per_model_method = summarize(selected_df, ["selection_policy", "model_label", "method"])
    per_model_overall = summarize(
        selected_df.assign(method="ALL"),
        ["selection_policy", "model_label", "method"],
    )
    overall_by_method = summarize(
        selected_df.assign(model_label="ALL"),
        ["selection_policy", "model_label", "method"],
    )
    overall_all_methods = summarize(
        selected_df.assign(model_label="ALL", method="ALL"),
        ["selection_policy", "model_label", "method"],
    )
    summary_df = pd.concat(
        [per_model_method, per_model_overall, overall_by_method, overall_all_methods],
        ignore_index=True,
    )
    summary_df["selection_policy"] = pd.Categorical(summary_df["selection_policy"], POLICY_ORDER, ordered=True)
    summary_df["method"] = pd.Categorical(summary_df["method"], METHOD_ORDER, ordered=True)
    summary_df = summary_df.sort_values(["model_label", "selection_policy", "method"]).reset_index(drop=True)
    summary_df["selection_policy"] = summary_df["selection_policy"].astype(str)
    summary_df["method"] = summary_df["method"].astype(str)

    cell_matrix_df = build_cell_matrix(selected_df)
    cell_matrix_df["method"] = pd.Categorical(cell_matrix_df["method"], METHOD_ORDER, ordered=True)
    cell_matrix_df = cell_matrix_df.sort_values(["model_label", "method", "case_id"]).reset_index(drop=True)
    cell_matrix_df["method"] = cell_matrix_df["method"].astype(str)

    selected_path = out_dir / SELECTED_CSV
    summary_path = out_dir / SUMMARY_CSV
    cell_matrix_path = out_dir / CELL_MATRIX_CSV
    summary_json_path = out_dir / SUMMARY_JSON
    readme_path = out_dir / README_MD

    selected_df.to_csv(selected_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    cell_matrix_df.to_csv(cell_matrix_path, index=False, encoding="utf-8-sig")
    summary_json_path.write_text(
        json.dumps(build_summary_json(summary_df, input_csv), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    readme_path.write_text(build_readme(), encoding="utf-8")

    print(selected_path)
    print(summary_path)
    print(cell_matrix_path)
    print(summary_json_path)
    print(readme_path)


if __name__ == "__main__":
    main()
