from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.shared import Inches


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DATA_DIR = ROOT / "outputs" / THREAD_ID / "multi_model_eval_data"
OUT_DOC = ROOT / "outputs" / THREAD_ID / "multi_model_observation.docx"


def style_doc(doc: Document) -> None:
    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)


def add_table(doc: Document, df: pd.DataFrame, max_rows: int | None = None) -> None:
    use_df = df if max_rows is None else df.head(max_rows)
    table = doc.add_table(rows=1, cols=len(use_df.columns))
    table.style = "Table Grid"
    for idx, col in enumerate(use_df.columns):
        table.rows[0].cells[idx].text = str(col)
    for _, row in use_df.iterrows():
        cells = table.add_row().cells
        for idx, col in enumerate(use_df.columns):
            value = row[col]
            if pd.isna(value):
                cells[idx].text = ""
            elif isinstance(value, float):
                cells[idx].text = f"{value:.3f}"
            else:
                cells[idx].text = str(value)


def strict_success_mask(df: pd.DataFrame) -> pd.Series:
    heldout_non_vacuous = (
        df["heldout_non_vacuous"].astype(bool)
        if "heldout_non_vacuous" in df.columns
        else df["heldout_antecedent_hit"].astype(bool)
    )
    return (
        df["heldout_correct_pass"].astype(bool)
        & df["heldout_buggy_fail"].astype(bool)
        & df["heldout_antecedent_hit"].astype(bool)
        & heldout_non_vacuous
    )


def aggregate_case_method(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (model_label, method, case_id), sub in df.groupby(
        ["model_label", "method", "case_id"], dropna=False
    ):
        strict_rate = float(strict_success_mask(sub).mean()) if len(sub) else 0.0
        dominant_failure = (
            sub["failure_mode"].value_counts().sort_values(ascending=False).index[0]
            if len(sub)
            else ""
        )
        best = sub.assign(
            best_score=(
                sub["correct_pass"].astype(int) * 4
                + sub["buggy_fail"].astype(int) * 4
                + sub["heldout_correct_pass"].astype(int) * 2
                + sub["heldout_buggy_fail"].astype(int) * 2
                + sub["antecedent_hit_buggy"].astype(int)
                - sub["trace_overfit"].astype(int) * 2
                - (sub["failure_mode"] == "compile_fail").astype(int) * 8
            )
        ).sort_values("best_score", ascending=False).iloc[0]
        rows.append(
            {
                "model_label": model_label,
                "method": method,
                "case_id": case_id,
                "candidate_count": int(len(sub)),
                "correct_pass_rate": float(sub["correct_pass"].mean()),
                "buggy_fail_rate": float(sub["buggy_fail"].mean()),
                "antecedent_hit_buggy_rate": float(sub["antecedent_hit_buggy"].mean()),
                "heldout_correct_pass_rate": float(sub["heldout_correct_pass"].mean()),
                "heldout_buggy_fail_rate": float(sub["heldout_buggy_fail"].mean()),
                "trace_overfit_rate": float(sub["trace_overfit"].mean()),
                "literal_hardcoding_rate": float(sub["literal_hardcoding"].mean()),
                "strict_success_rate": strict_rate,
                "dominant_failure_mode": dominant_failure,
                "best_candidate_text": best["assertion_text"],
            }
        )
    return pd.DataFrame(rows)


def family_summary(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for (model_label, method), sub in df.groupby(["model_label", "method"], dropna=False):
        failure_counts = sub["failure_mode"].value_counts()
        records.append(
            {
                "model_label": model_label,
                "method": method,
                "candidate_count": int(len(sub)),
                "strict_success_rate": float(strict_success_mask(sub).mean()),
                "correct_pass_rate": float(sub["correct_pass"].mean()),
                "buggy_fail_rate": float(sub["buggy_fail"].mean()),
                "antecedent_hit_buggy_rate": float(sub["antecedent_hit_buggy"].mean()),
                "heldout_correct_pass_rate": float(sub["heldout_correct_pass"].mean()),
                "heldout_buggy_fail_rate": float(sub["heldout_buggy_fail"].mean()),
                "trace_overfit_rate": float(sub["trace_overfit"].mean()),
                "literal_hardcoding_rate": float(sub["literal_hardcoding"].mean()),
                "vacuity_rate": float((sub["failure_mode"] == "vacuity").mean()),
                "too_weak_rate": float((sub["failure_mode"] == "too_weak").mean()),
                "too_strong_rate": float((sub["failure_mode"] == "too_strong").mean()),
                "compile_fail_rate": float((sub["failure_mode"] == "compile_fail").mean()),
                "overfit_suspect_rate": float((sub["failure_mode"] == "overfit_suspect").mean()),
                "success_rate": float((sub["failure_mode"] == "success").mean()),
                "dominant_failure_mode": failure_counts.index[0] if len(failure_counts) else "",
            }
        )
    return pd.DataFrame(records).sort_values(["model_label", "method"]).reset_index(drop=True)


def compare_trace_methods(case_method_df: pd.DataFrame, model_label: str) -> pd.DataFrame:
    pivot_rows = []
    model_df = case_method_df.loc[case_method_df["model_label"] == model_label].copy()
    for case_id, sub in model_df.groupby("case_id", dropna=False):
        lookup = {row["method"]: row for _, row in sub.iterrows()}
        rtl = lookup.get("spec_rtl_only")
        raw = lookup.get("spec_rtl_raw_trace")
        summ = lookup.get("spec_rtl_trace_summary")
        abst = lookup.get("spec_rtl_abstracted_trace_summary")

        def delta(a: pd.Series | None, b: pd.Series | None, col: str) -> float | None:
            if a is None or b is None:
                return None
            return float(a[col]) - float(b[col])

        pivot_rows.append(
            {
                "case_id": case_id,
                "raw_minus_rtl_buggy_fail": delta(raw, rtl, "buggy_fail_rate"),
                "summary_minus_rtl_buggy_fail": delta(summ, rtl, "buggy_fail_rate"),
                "abstracted_minus_rtl_buggy_fail": delta(abst, rtl, "buggy_fail_rate"),
                "raw_minus_summary_trace_overfit": delta(raw, summ, "trace_overfit_rate"),
                "abstracted_minus_summary_trace_overfit": delta(abst, summ, "trace_overfit_rate"),
                "raw_minus_summary_literal_hardcoding": delta(raw, summ, "literal_hardcoding_rate"),
                "abstracted_minus_summary_literal_hardcoding": delta(abst, summ, "literal_hardcoding_rate"),
                "raw_minus_summary_correct_pass": delta(raw, summ, "correct_pass_rate"),
                "summary_minus_raw_antecedent_hit": delta(summ, raw, "antecedent_hit_buggy_rate"),
                "best_trace_family": choose_best_trace_family(lookup),
            }
        )
    return pd.DataFrame(pivot_rows).sort_values("case_id").reset_index(drop=True)


def choose_best_trace_family(lookup: dict[str, pd.Series]) -> str:
    candidates: list[tuple[str, float]] = []
    for method, row in lookup.items():
        score = (
            float(row["strict_success_rate"]) * 5.0
            + float(row["buggy_fail_rate"]) * 2.0
            + float(row["correct_pass_rate"]) * 1.5
            + float(row["antecedent_hit_buggy_rate"]) * 1.0
            - float(row["trace_overfit_rate"]) * 2.0
            - float(row["literal_hardcoding_rate"]) * 1.0
        )
        candidates.append((method, score))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: item[1], reverse=True)[0][0]


def build_observation_doc() -> None:
    run_meta = json.loads((DATA_DIR / "multi_model_run_meta.json").read_text(encoding="utf-8"))
    model_specs = run_meta.get("model_specs", run_meta.get("active_model_specs", []))
    method_specs = run_meta.get("method_specs", run_meta.get("active_method_specs", []))
    summary_df = pd.read_csv(DATA_DIR / "multi_model_summary.csv")
    raw_df = pd.read_csv(DATA_DIR / "multi_model_results_raw.csv")
    prompt_df = pd.read_csv(DATA_DIR / "multi_model_prompt_log.csv")

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
        if col in raw_df.columns:
            raw_df[col] = raw_df[col].astype(bool)

    model_method_df = family_summary(raw_df)
    case_method_df = aggregate_case_method(raw_df)

    doc = Document()
    style_doc(doc)
    doc.add_heading("multi model small evaluation observation", level=0)
    doc.add_paragraph(
        "This note summarizes the 5-case small-scale comparison used to test whether the trace double-edge effect "
        "appears only for one model family or shows up more broadly."
    )

    doc.add_heading("Experiment setup", level=1)
    setup_df = pd.DataFrame(
        [
            ["representative_case_count", len(run_meta.get("representative_case_ids", []))],
            ["model_count", len(model_specs)],
            ["method_count", len(method_specs)],
            ["candidates_per_cell", run_meta.get("candidates_per_cell", "")],
            ["use_property_compile_mode", run_meta.get("use_property_compile_mode", "")],
        ],
        columns=["field", "value"],
    )
    add_table(doc, setup_df)

    doc.add_heading("Model × method summary", level=1)
    keep_cols = [
        "model_label",
        "method",
        "candidate_count",
        "strict_success_rate",
        "correct_pass_rate",
        "buggy_fail_rate",
        "antecedent_hit_buggy_rate",
        "heldout_buggy_fail_rate",
        "trace_overfit_rate",
        "literal_hardcoding_rate",
        "vacuity_rate",
        "too_weak_rate",
        "too_strong_rate",
        "overfit_suspect_rate",
        "dominant_failure_mode",
    ]
    add_table(doc, model_method_df[keep_cols])

    doc.add_heading("Cross-model failure-mode similarity", level=1)
    if raw_df["model_label"].nunique() < 2:
        doc.add_paragraph(
            "Only one model is present in the current run, so this artifact can describe the GPT-side pattern "
            "but cannot yet make a true cross-model similarity claim."
        )
    else:
        pivot = model_method_df[
            [
                "model_label",
                "method",
                "vacuity_rate",
                "too_weak_rate",
                "too_strong_rate",
                "overfit_suspect_rate",
            ]
        ].copy()
        add_table(doc, pivot)
        for method, sub in pivot.groupby("method", dropna=False):
            span = {
                metric: float(sub[metric].max() - sub[metric].min())
                for metric in [
                    "vacuity_rate",
                    "too_weak_rate",
                    "too_strong_rate",
                    "overfit_suspect_rate",
                ]
            }
            dominant_metric = sorted(span.items(), key=lambda item: item[1], reverse=True)[0][0]
            doc.add_paragraph(
                f"For {method}, the largest cross-model spread is on {dominant_metric} "
                f"(range={span[dominant_metric]:.3f}).",
                style="List Bullet",
            )

    doc.add_heading("Trace double-edge pattern", level=1)
    for model_label in sorted(case_method_df["model_label"].dropna().unique()):
        doc.add_paragraph(f"Model: {model_label}")
        comp_df = compare_trace_methods(case_method_df, model_label)
        add_table(doc, comp_df)

        model_family = model_method_df.loc[model_method_df["model_label"] == model_label].copy()
        raw_row = model_family.loc[model_family["method"] == "spec_rtl_raw_trace"]
        sum_row = model_family.loc[model_family["method"] == "spec_rtl_trace_summary"]
        abs_row = model_family.loc[model_family["method"] == "spec_rtl_abstracted_trace_summary"]
        rtl_row = model_family.loc[model_family["method"] == "spec_rtl_only"]

        notes: list[str] = []
        if not raw_row.empty and not rtl_row.empty:
            raw_bug_delta = float(raw_row.iloc[0]["buggy_fail_rate"] - rtl_row.iloc[0]["buggy_fail_rate"])
            raw_overfit_delta = float(raw_row.iloc[0]["trace_overfit_rate"] - rtl_row.iloc[0]["trace_overfit_rate"])
            notes.append(
                f"Raw trace vs spec+RTL: buggy_fail delta={raw_bug_delta:.3f}, trace_overfit delta={raw_overfit_delta:.3f}."
            )
        if not sum_row.empty and not rtl_row.empty:
            sum_bug_delta = float(sum_row.iloc[0]["buggy_fail_rate"] - rtl_row.iloc[0]["buggy_fail_rate"])
            sum_correct_delta = float(sum_row.iloc[0]["correct_pass_rate"] - rtl_row.iloc[0]["correct_pass_rate"])
            notes.append(
                f"Trace summary vs spec+RTL: buggy_fail delta={sum_bug_delta:.3f}, correct_pass delta={sum_correct_delta:.3f}."
            )
        if not abs_row.empty and not sum_row.empty:
            abs_overfit_delta = float(abs_row.iloc[0]["trace_overfit_rate"] - sum_row.iloc[0]["trace_overfit_rate"])
            abs_literal_delta = float(abs_row.iloc[0]["literal_hardcoding_rate"] - sum_row.iloc[0]["literal_hardcoding_rate"])
            notes.append(
                f"Abstracted summary vs normal summary: trace_overfit delta={abs_overfit_delta:.3f}, "
                f"literal_hardcoding delta={abs_literal_delta:.3f}."
            )
        for note in notes:
            doc.add_paragraph(note, style="List Bullet")

    doc.add_heading("Representative case notes", level=1)
    case_note_rows: list[dict[str, object]] = []
    for (model_label, case_id), sub in case_method_df.groupby(["model_label", "case_id"], dropna=False):
        best = sub.sort_values(
            [
                "strict_success_rate",
                "buggy_fail_rate",
                "correct_pass_rate",
                "antecedent_hit_buggy_rate",
            ],
            ascending=[False, False, False, False],
        ).iloc[0]
        worst = sub.sort_values(
            ["strict_success_rate", "trace_overfit_rate", "vacuity_rate" if "vacuity_rate" in sub.columns else "buggy_fail_rate"],
            ascending=[True, False, False],
        ).iloc[0]
        case_note_rows.append(
            {
                "model_label": model_label,
                "case_id": case_id,
                "best_method": best["method"],
                "best_strict_success_rate": best["strict_success_rate"],
                "worst_method": worst["method"],
                "worst_dominant_failure_mode": worst["dominant_failure_mode"],
                "best_candidate_text": best["best_candidate_text"],
            }
        )
    add_table(doc, pd.DataFrame(case_note_rows))

    doc.add_heading("Prompt logging coverage", level=1)
    prompt_overview = (
        prompt_df[["model_label", "case_id", "method", "prompt_path"]]
        .drop_duplicates()
        .sort_values(["model_label", "case_id", "method"])
        .reset_index(drop=True)
    )
    add_table(doc, prompt_overview, max_rows=20)

    doc.save(OUT_DOC)


if __name__ == "__main__":
    build_observation_doc()
