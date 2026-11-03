from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.shared import Inches


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DATA_DIR = ROOT / "outputs" / THREAD_ID / "trace_selection_data"
OUT_DOCX = ROOT / "outputs" / THREAD_ID / "trace_quality_score_definition.docx"


def style_doc(doc: Document) -> None:
    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)


def add_table(doc: Document, df: pd.DataFrame) -> None:
    table = doc.add_table(rows=1, cols=len(df.columns))
    table.style = "Table Grid"
    for idx, col in enumerate(df.columns):
        table.rows[0].cells[idx].text = str(col)
    for _, row in df.iterrows():
        cells = table.add_row().cells
        for idx, col in enumerate(df.columns):
            value = row[col]
            if pd.isna(value):
                cells[idx].text = ""
            else:
                cells[idx].text = str(value)


def main() -> None:
    selected_cases = json.loads((DATA_DIR / "selected_cases.json").read_text(encoding="utf-8"))
    selected_df = pd.read_csv(DATA_DIR / "trace_quality_selected_windows.csv")

    doc = Document()
    style_doc(doc)
    doc.add_heading("trace quality score definition", level=0)
    doc.add_paragraph(
        "This prototype treats each candidate trace as a fixed-length aligned good/bad trace snippet. "
        "For each case, we enumerate all windows over the seen trace pair, score every window, then select one "
        "high-quality snippet and one low-quality snippet for LLM prompting."
    )

    doc.add_heading("Scoring dimensions", level=1)
    scoring_df = pd.DataFrame(
        [
            {
                "dimension": "divergence_clear",
                "range": "0..2",
                "meaning": "Whether the snippet contains a clear first good/bad divergence, preferably after a short matched prelude.",
            },
            {
                "dimension": "antecedent_cover",
                "range": "0..2",
                "meaning": "Whether the snippet visibly covers the bug-triggering condition rather than only post-bug aftermath.",
            },
            {
                "dimension": "literal_risk",
                "range": "0..2 penalty",
                "meaning": "Penalty for concrete lure literals such as multi-hot masks, FIFO depth boundaries, or pointer values that do not reappear on held-out traces.",
            },
            {
                "dimension": "temporal_depth",
                "range": "0..2",
                "meaning": "Whether the snippet preserves enough cross-cycle context to show trigger-to-effect timing.",
            },
            {
                "dimension": "heldout_consistency",
                "range": "0..2",
                "meaning": "Whether held-out traces show the same trigger/effect relation, so the observed snippet is less likely to be a one-off artifact.",
            },
        ]
    )
    add_table(doc, scoring_df)

    doc.add_heading("Total score", level=1)
    doc.add_paragraph("total_score = divergence_clear + antecedent_cover + temporal_depth + heldout_consistency - literal_risk")
    doc.add_paragraph(
        "High-quality snippets are ranked by higher total_score, then by stronger antecedent coverage, clearer divergence, better held-out consistency, and lower literal risk. "
        "Low-quality snippets use the opposite ranking."
    )

    doc.add_heading("How each dimension is interpreted", level=1)
    bullets = [
        "divergence_clear=2 when the snippet shows one or more matching cycles before the first divergence; divergence_clear=1 when the snippet starts at or after the divergence; divergence_clear=0 when good/bad never differ inside the snippet.",
        "antecedent_cover=2 when the window includes both the bug trigger and its visible effect; antecedent_cover=1 when the trigger appears but alignment is weak; antecedent_cover=0 when the trigger is absent.",
        "literal_risk=2 when the focus region contains nontrivial lure literals that do not recur on held-out traces; literal_risk=1 when concrete boundary literals are present but not uniquely suspicious; literal_risk=0 when the snippet is mostly relational/boolean.",
        "temporal_depth=2 for temporal cases when the snippet includes the trigger and at least one cycle of aftermath; temporal_depth=1 for same-cycle cases that still expose the trigger; temporal_depth=0 when the snippet lacks useful timing context.",
        "heldout_consistency=2 when held-out traces contain the same trigger/effect relation, =1 when they contain the trigger with weaker alignment evidence, and =0 otherwise.",
    ]
    for item in bullets:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Selected cases", level=1)
    case_df = pd.DataFrame(selected_cases)
    add_table(doc, case_df[["case_id", "bug_class", "temporal_kind", "selection_reason"]])

    doc.add_heading("Chosen high/low snippets", level=1)
    preview_df = selected_df[
        [
            "case_id",
            "selected_trace_quality",
            "window_start_cycle",
            "window_end_cycle",
            "divergence_clear",
            "antecedent_cover",
            "literal_risk",
            "temporal_depth",
            "heldout_consistency",
            "total_score",
            "selection_notes",
        ]
    ].copy()
    add_table(doc, preview_df)

    doc.save(OUT_DOCX)
    print(OUT_DOCX)


if __name__ == "__main__":
    main()
