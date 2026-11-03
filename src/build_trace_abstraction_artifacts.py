from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.shared import Inches


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DATA_DIR = ROOT / "outputs" / THREAD_ID / "trace_abstraction_data"
OUT_DIR = ROOT / "outputs" / THREAD_ID
OUT_PROMPTS_DOCX = OUT_DIR / "8个case_trace_abstraction_prompts.docx"
OUT_SUMMARY_DOCX = OUT_DIR / "trace_abstraction_summary.docx"

BOOL_COLS = [
    "compile_ok",
    "correct_pass",
    "buggy_fail",
    "antecedent_hit",
    "non_vacuous",
    "heldout_correct_pass",
    "heldout_buggy_fail",
    "trace_overfit",
    "semantic_reasonable",
]


def load_selected_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "selected_cases.json").read_text(encoding="utf-8"))


def load_results() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "trace_abstraction_results_raw.csv")
    for col in BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(bool)
    return df


def build_summary_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    grouped = (
        df.groupby(["case_id", "prompt_variant"], dropna=False)[BOOL_COLS]
        .agg(["sum", "mean"])
        .reset_index()
    )
    grouped.columns = [
        "_".join([str(x) for x in col if str(x) != ""]).rstrip("_")
        for col in grouped.columns.to_flat_index()
    ]
    grouped = grouped.rename(columns={"case_id_": "case_id", "prompt_variant_": "prompt_variant"})

    overall = df.groupby(["prompt_variant"], dropna=False)[BOOL_COLS].agg(["sum", "mean"]).reset_index()
    overall.columns = [
        "_".join([str(x) for x in col if str(x) != ""]).rstrip("_")
        for col in overall.columns.to_flat_index()
    ]
    overall = overall.rename(columns={"prompt_variant_": "prompt_variant"})

    case_variant_pivot = grouped.pivot(index="case_id", columns="prompt_variant")
    case_variant_pivot.columns = [f"{b}__{a}" for a, b in case_variant_pivot.columns]
    case_variant_pivot = case_variant_pivot.reset_index()
    return grouped, overall, case_variant_pivot


def style_doc(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = normal.font.size
    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)


def add_table(doc: Document, df: pd.DataFrame, *, max_rows: int | None = None) -> None:
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
                if abs(value - round(value)) < 1e-9:
                    cells[idx].text = str(int(round(value)))
                else:
                    cells[idx].text = f"{value:.3f}"
            else:
                cells[idx].text = str(value)


def build_prompts_doc(selected_cases: list[dict[str, Any]]) -> None:
    doc = Document()
    style_doc(doc)
    doc.add_heading("8-case trace abstraction prompts", level=0)
    doc.add_paragraph(
        "This document records the 8 selected failure cases, the selection rationale, "
        "and the three trace inputs used in the trace abstraction prototype."
    )

    overview = pd.DataFrame(
        [
            {
                "case_id": item["case_id"],
                "selection_tags": item["selection_tags"],
                "selection_reason": item["selection_reason"],
            }
            for item in selected_cases
        ]
    )
    doc.add_heading("Selected cases overview", level=1)
    add_table(doc, overview)

    for item in selected_cases:
        doc.add_section(WD_SECTION_START.NEW_PAGE)
        doc.add_heading(item["case_id"], level=1)
        doc.add_paragraph(f"Selection tags: {item['selection_tags']}")
        doc.add_paragraph(f"Selection reason: {item['selection_reason']}")

        doc.add_heading("Specification", level=2)
        doc.add_paragraph(item["spec"])

        doc.add_heading("Raw trace input", level=2)
        doc.add_paragraph(item["raw_trace_input"])

        doc.add_heading("Normal trace summary", level=2)
        doc.add_paragraph(item["normal_trace_summary"])

        doc.add_heading("Abstracted trace summary", level=2)
        doc.add_paragraph(item["abstracted_trace_summary"])

    doc.save(OUT_PROMPTS_DOCX)


def best_variant_row(case_df: pd.DataFrame) -> pd.Series:
    ranked = case_df.sort_values(
        by=[
            "buggy_fail_mean",
            "correct_pass_mean",
            "heldout_buggy_fail_mean",
            "trace_overfit_mean",
        ],
        ascending=[False, False, False, True],
    )
    return ranked.iloc[0]


def build_summary_doc(grouped: pd.DataFrame, overall: pd.DataFrame, case_variant_pivot: pd.DataFrame) -> None:
    doc = Document()
    style_doc(doc)
    doc.add_heading("trace abstraction summary", level=0)
    doc.add_paragraph(
        "This summary compares raw trace, normal trace summary, and abstracted trace summary "
        "for the 8-case prototype. Each case/variant contains at least 5 candidates."
    )

    doc.add_heading("Overall by prompt variant", level=1)
    add_table(doc, overall)

    doc.add_heading("Per-case best variant", level=1)
    best_rows = []
    for case_id, sub in grouped.groupby("case_id", dropna=False):
        row = best_variant_row(sub)
        best_rows.append(
            {
                "case_id": case_id,
                "best_variant": row["prompt_variant"],
                "buggy_fail_mean": row["buggy_fail_mean"],
                "correct_pass_mean": row["correct_pass_mean"],
                "heldout_buggy_fail_mean": row["heldout_buggy_fail_mean"],
                "trace_overfit_mean": row["trace_overfit_mean"],
            }
        )
    add_table(doc, pd.DataFrame(best_rows))

    def metric_map(df: pd.DataFrame) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for _, row in df.iterrows():
            out[str(row["prompt_variant"])] = {
                col: float(row[col]) for col in df.columns if col.endswith("_mean")
            }
        return out

    metrics = metric_map(overall)
    raw = metrics.get("raw_trace", {})
    normal = metrics.get("normal_trace_summary", {})
    abstracted = metrics.get("abstracted_trace_summary", {})

    findings = []
    if abstracted and raw:
        findings.append(
            "Abstracted summary vs raw trace: "
            f"correct_pass {abstracted.get('correct_pass_mean', 0):.3f} vs {raw.get('correct_pass_mean', 0):.3f}, "
            f"buggy_fail {abstracted.get('buggy_fail_mean', 0):.3f} vs {raw.get('buggy_fail_mean', 0):.3f}, "
            f"trace_overfit {abstracted.get('trace_overfit_mean', 0):.3f} vs {raw.get('trace_overfit_mean', 0):.3f}."
        )
    if normal and raw:
        findings.append(
            "Normal summary vs raw trace: "
            f"correct_pass {normal.get('correct_pass_mean', 0):.3f} vs {raw.get('correct_pass_mean', 0):.3f}, "
            f"buggy_fail {normal.get('buggy_fail_mean', 0):.3f} vs {raw.get('buggy_fail_mean', 0):.3f}, "
            f"trace_overfit {normal.get('trace_overfit_mean', 0):.3f} vs {raw.get('trace_overfit_mean', 0):.3f}."
        )
    if abstracted and normal:
        findings.append(
            "Abstracted summary vs normal summary: "
            f"heldout_buggy_fail {abstracted.get('heldout_buggy_fail_mean', 0):.3f} vs {normal.get('heldout_buggy_fail_mean', 0):.3f}, "
            f"semantic_reasonable {abstracted.get('semantic_reasonable_mean', 0):.3f} vs {normal.get('semantic_reasonable_mean', 0):.3f}."
        )

    doc.add_heading("High-level findings", level=1)
    for item in findings:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Case x variant matrix", level=1)
    add_table(doc, case_variant_pivot, max_rows=len(case_variant_pivot))

    doc.save(OUT_SUMMARY_DOCX)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    selected_cases = load_selected_cases()
    raw_df = load_results()
    grouped, overall, case_variant_pivot = build_summary_tables(raw_df)
    build_prompts_doc(selected_cases)
    build_summary_doc(grouped, overall, case_variant_pivot)
    print(OUT_PROMPTS_DOCX)
    print(OUT_SUMMARY_DOCX)


if __name__ == "__main__":
    main()
