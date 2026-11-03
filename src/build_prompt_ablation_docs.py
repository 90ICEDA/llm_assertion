from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.shared import Inches


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DATA_DIR = ROOT / "outputs" / THREAD_ID / "prompt_ablation_data"
OUT_DESIGN = ROOT / "outputs" / THREAD_ID / "prompt_ablation_design.docx"
OUT_SUMMARY = ROOT / "outputs" / THREAD_ID / "prompt_ablation_summary.docx"


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


def best_variant_text(summary_df: pd.DataFrame, metric: str) -> str:
    ranked = summary_df.sort_values(
        [metric, "strict_success_rate", "heldout_success_rate", "buggy_fail_rate"],
        ascending=[False, False, False, False],
    )
    top = ranked.iloc[0]
    return f"{top['prompt_variant']} ({metric}={float(top[metric]):.3f})"


def lowest_variant_text(summary_df: pd.DataFrame, metric: str) -> str:
    ranked = summary_df.sort_values(
        [metric, "strict_success_rate", "heldout_success_rate"],
        ascending=[True, False, False],
    )
    top = ranked.iloc[0]
    return f"{top['prompt_variant']} ({metric}={float(top[metric]):.3f})"


def build_design_doc() -> None:
    prompt_design = pd.read_csv(DATA_DIR / "prompt_ablation_prompt_design.csv")
    run_meta = json.loads((DATA_DIR / "prompt_ablation_run_meta.json").read_text(encoding="utf-8"))

    overview = (
        prompt_design[
            [
                "prompt_variant",
                "constraint_family",
                "constraint_focus",
                "extra_instruction",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    cases = (
        prompt_design[["case_id", "selection_tags", "selection_reason"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    doc = Document()
    style_doc(doc)
    doc.add_heading("prompt ablation design", level=0)
    doc.add_paragraph(
        "This prototype keeps the case set fixed and feeds the same sanitized abstracted trace summaries to every prompt arm. "
        "The only intended difference is the prompt-side constraint."
    )

    doc.add_heading("Experiment setup", level=1)
    setup_df = pd.DataFrame(
        [
            ["model_name", run_meta["model_name"]],
            ["selected_case_count", run_meta["selected_case_count"]],
            ["candidates_per_prompt", run_meta["candidates_per_prompt"]],
            ["prompt_variant_count", len(run_meta["prompt_variants"])],
            ["use_property_compile_mode", run_meta["use_property_compile_mode"]],
        ],
        columns=["field", "value"],
    )
    add_table(doc, setup_df)

    doc.add_heading("Why the abstracted summaries were sanitized", level=1)
    doc.add_paragraph(
        "The previous trace-abstraction artifact included a final bullet such as 'Do not hardcode ...'. "
        "To make prompt ablation fair, this prototype removes that meta-instruction from the trace summary payload. "
        "Otherwise the control arm would still inherit an anti-hardcoding reminder from the input summary itself."
    )

    doc.add_heading("Prompt variants", level=1)
    add_table(doc, overview)

    doc.add_heading("Selected 8 cases", level=1)
    add_table(doc, cases)

    sample_rows = (
        prompt_design[
            [
                "case_id",
                "prompt_variant",
                "abstracted_trace_summary_original",
                "abstracted_trace_summary_sanitized",
                "extra_instruction",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    doc.add_heading("Example sanitized summary + prompt constraint", level=1)
    add_table(doc, sample_rows, max_rows=6)

    doc.save(OUT_DESIGN)


def build_summary_doc() -> None:
    summary_df = pd.read_csv(DATA_DIR / "prompt_ablation_summary_by_prompt.csv")
    case_prompt_df = pd.read_csv(DATA_DIR / "prompt_ablation_case_prompt_summary.csv")
    result_df = pd.read_csv(DATA_DIR / "prompt_ablation_results_raw.csv")

    doc = Document()
    style_doc(doc)
    doc.add_heading("prompt ablation summary", level=0)
    doc.add_paragraph(
        "This summary compares six prompt constraints on the same 8-case abstracted-trace batch. "
        "All metrics below are candidate-level unless explicitly described as case-level."
    )

    doc.add_heading("Prompt-level ranking", level=1)
    add_table(
        doc,
        summary_df[
            [
                "prompt_variant",
                "constraint_family",
                "compile_ok_rate",
                "correct_pass_rate",
                "buggy_fail_rate",
                "antecedent_hit_rate",
                "heldout_success_rate",
                "strict_success_rate",
                "trace_overfit_rate",
                "literal_hardcoding_rate",
                "uses_temporal_feature_rate",
            ]
        ],
    )

    findings = [
        f"Highest strict success rate: {best_variant_text(summary_df, 'strict_success_rate')}.",
        f"Highest held-out success rate: {best_variant_text(summary_df, 'heldout_success_rate')}.",
        f"Highest buggy-fail rate: {best_variant_text(summary_df, 'buggy_fail_rate')}.",
        f"Lowest literal-hardcoding rate: {lowest_variant_text(summary_df, 'literal_hardcoding_rate')}.",
    ]
    for item in findings:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Case-level best prompt by strict success", level=1)
    best_rows = []
    for case_id, sub in case_prompt_df.groupby("case_id", dropna=False):
        best = sub.sort_values(
            [
                "strict_success_rate",
                "heldout_success_rate",
                "buggy_fail_rate",
                "correct_pass_rate",
                "antecedent_hit_rate",
            ],
            ascending=[False, False, False, False, False],
        ).iloc[0]
        best_rows.append(
            {
                "case_id": case_id,
                "best_prompt_variant": best["prompt_variant"],
                "strict_success_rate": best["strict_success_rate"],
                "heldout_success_rate": best["heldout_success_rate"],
                "buggy_fail_rate": best["buggy_fail_rate"],
                "correct_pass_rate": best["correct_pass_rate"],
            }
        )
    add_table(doc, pd.DataFrame(best_rows))

    doc.add_heading("Per-family interpretation", level=1)
    fam_means = (
        summary_df.groupby("constraint_family", dropna=False)[
            [
                "compile_ok_rate",
                "correct_pass_rate",
                "buggy_fail_rate",
                "antecedent_hit_rate",
                "heldout_success_rate",
                "strict_success_rate",
                "trace_overfit_rate",
                "literal_hardcoding_rate",
                "uses_temporal_feature_rate",
            ]
        ]
        .mean()
        .reset_index()
    )
    add_table(doc, fam_means)

    doc.add_heading("Notable observations", level=1)
    observations = []
    best_strict = summary_df.sort_values(
        ["strict_success_rate", "heldout_success_rate", "buggy_fail_rate", "correct_pass_rate"],
        ascending=[False, False, False, False],
    ).iloc[0]
    observations.append(
        "No single prompt dominates every metric. "
        f"On the strict success metric, the strongest arm is {best_strict['prompt_variant']} "
        f"(strict_success_rate={best_strict['strict_success_rate']:.3f}, buggy_fail_rate={best_strict['buggy_fail_rate']:.3f})."
    )
    if "remind_antecedent_must_trigger" in set(summary_df["prompt_variant"]):
        row = summary_df.loc[summary_df["prompt_variant"] == "remind_antecedent_must_trigger"].iloc[0]
        observations.append(
            f"Antecedent-trigger reminder: antecedent_hit_rate={row['antecedent_hit_rate']:.3f}, "
            f"strict_success_rate={row['strict_success_rate']:.3f}."
        )
    if "remind_avoid_hardcoding" in set(summary_df["prompt_variant"]):
        row = summary_df.loc[summary_df["prompt_variant"] == "remind_avoid_hardcoding"].iloc[0]
        observations.append(
            f"Anti-hardcoding reminder: literal_hardcoding_rate={row['literal_hardcoding_rate']:.3f}, "
            f"heldout_success_rate={row['heldout_success_rate']:.3f}, correct_pass_rate={row['correct_pass_rate']:.3f}."
        )
    if "remind_use_temporal_operator" in set(summary_df["prompt_variant"]):
        row = summary_df.loc[summary_df["prompt_variant"] == "remind_use_temporal_operator"].iloc[0]
        observations.append(
            f"Temporal-operator reminder: uses_temporal_feature_rate={row['uses_temporal_feature_rate']:.3f}, "
            f"compile_ok_rate={row['compile_ok_rate']:.3f}."
        )
    if "remind_heldout_generalization" in set(summary_df["prompt_variant"]):
        row = summary_df.loc[summary_df["prompt_variant"] == "remind_heldout_generalization"].iloc[0]
        observations.append(
            f"Held-out generalization reminder: heldout_success_rate={row['heldout_success_rate']:.3f}, "
            f"trace_overfit_rate={row['trace_overfit_rate']:.3f}, literal_hardcoding_rate={row['literal_hardcoding_rate']:.3f}."
        )
    for item in observations:
        doc.add_paragraph(item, style="List Bullet")

    compile_fail_rows = result_df[~result_df["compile_ok"]].copy()
    if not compile_fail_rows.empty:
        brief = (
            compile_fail_rows.groupby("prompt_variant", dropna=False)
            .size()
            .reset_index(name="compile_fail_count")
            .sort_values("compile_fail_count", ascending=False)
        )
        doc.add_heading("Compile-fail concentration", level=1)
        add_table(doc, brief)

    doc.save(OUT_SUMMARY)


def main() -> None:
    build_design_doc()
    build_summary_doc()
    print(OUT_DESIGN)
    print(OUT_SUMMARY)


if __name__ == "__main__":
    main()
