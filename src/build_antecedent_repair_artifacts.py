from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.shared import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DATA_DIR = ROOT / "outputs" / THREAD_ID / "antecedent_repair_data"
OUT_DIR = ROOT / "outputs" / THREAD_ID


def style_doc(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)


def add_table(doc: Document, df: pd.DataFrame) -> None:
    table = doc.add_table(rows=1, cols=len(df.columns))
    table.style = "Table Grid"
    for idx, col in enumerate(df.columns):
        table.rows[0].cells[idx].text = str(col)
    for _, row in df.iterrows():
        cells = table.add_row().cells
        for idx, col in enumerate(df.columns):
            val = row[col]
            cells[idx].text = "" if pd.isna(val) else str(val)


def main() -> None:
    case_df = pd.read_csv(DATA_DIR / "antecedent_repair_case_summary.csv")
    cand_df = pd.read_csv(DATA_DIR / "antecedent_repair_candidate_results.csv")
    prompt_df = pd.read_csv(DATA_DIR / "antecedent_repair_prompts.csv")

    selected_case_meta = case_df[
        [
            "case_id",
            "module",
            "bug_name",
            "bug_class",
            "method",
            "method_label",
            "prompt_type",
            "selection_reason",
            "trigger_condition_summary",
            "antecedent_failure_diagnosis",
            "original_assertion",
            "original_antecedent",
            "locked_implication",
            "locked_consequent",
        ]
    ].copy()

    aggregate = pd.DataFrame(
        [
            {"metric": "selected_case_count", "value": int(len(case_df))},
            {"metric": "original_correct_pass_count", "value": int(case_df["original_correct_pass"].sum())},
            {"metric": "repaired_correct_pass_count", "value": int(case_df["repaired_correct_pass"].sum())},
            {"metric": "correct_pass_preserved_count", "value": int(case_df["correct_pass_preserved"].sum())},
            {"metric": "fail_on_buggy_improved_count", "value": int(case_df["fail_on_buggy_improved"].sum())},
            {"metric": "antecedent_hit_improved_count", "value": int(case_df["antecedent_hit_improved"].sum())},
            {"metric": "false_positive_introduced_count", "value": int(case_df["false_positive_introduced"].sum())},
            {"metric": "heldout_failure_introduced_count", "value": int(case_df["heldout_failure_introduced"].sum())},
            {
                "metric": "candidate_level_buggy_improve_with_fp_count",
                "value": int(
                    cand_df[
                        (cand_df["fail_on_buggy"] == True)
                        & (cand_df["false_positive_introduced"] == True)
                    ].shape[0]
                ),
            },
        ]
    )
    aggressive = cand_df[
        (cand_df["fail_on_buggy"] == True) | (cand_df["antecedent_hit"] == True)
    ].copy()
    aggressive = aggressive[
        [
            "case_id",
            "candidate_index",
            "repaired_antecedent",
            "compile_ok",
            "correct_pass",
            "fail_on_buggy",
            "antecedent_hit",
            "heldout_correct_pass",
            "heldout_buggy_fail",
            "false_positive_introduced",
            "heldout_failure_introduced",
        ]
    ]

    aggregate.to_csv(DATA_DIR / "antecedent_repair_aggregate_summary.csv", index=False, encoding="utf-8-sig")
    aggressive.to_csv(DATA_DIR / "antecedent_repair_aggressive_candidates.csv", index=False, encoding="utf-8-sig")
    selected_case_meta.to_csv(DATA_DIR / "antecedent_repair_selected_cases.csv", index=False, encoding="utf-8-sig")
    (DATA_DIR / "selected_repair_cases.json").write_text(
        json.dumps(selected_case_meta.to_dict(orient="records"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary_json = {
        row["metric"]: int(row["value"]) if float(row["value"]).is_integer() else float(row["value"])
        for _, row in aggregate.iterrows()
    }
    (DATA_DIR / "antecedent_repair_summary.json").write_text(
        json.dumps(summary_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    doc = Document()
    style_doc(doc)
    doc.add_heading("Antecedent Repair Prompts", level=0)
    doc.add_paragraph(
        "Prototype scope: 8 antecedent_not_triggered cases. "
        "For each case, the original LLM assertion is preserved except for antecedent repair candidates; "
        "the implication operator and consequent remain locked."
    )

    doc.add_heading("Aggregate summary", level=1)
    add_table(doc, aggregate)

    doc.add_heading("Selected cases overview", level=1)
    add_table(
        doc,
        case_df[
            [
                "case_id",
                "module",
                "bug_name",
                "bug_class",
                "method_label",
                "prompt_type",
                "correct_pass_preserved",
                "fail_on_buggy_improved",
                "antecedent_hit_improved",
            ]
        ],
    )

    for _, row in case_df.iterrows():
        doc.add_page_break()
        doc.add_heading(str(row["case_id"]), level=1)
        doc.add_paragraph(f"Module: {row['module']}")
        doc.add_paragraph(f"Bug: {row['bug_name']} ({row['bug_class']})")
        doc.add_paragraph(f"Original method: {row['method_label']} / {row['prompt_type']}")
        doc.add_paragraph(f"Selection reason: {row['selection_reason']}")

        doc.add_heading("Original assertion", level=2)
        doc.add_paragraph(str(row["original_assertion"]))

        doc.add_heading("Antecedent failure diagnosis", level=2)
        doc.add_paragraph(str(row["antecedent_failure_diagnosis"]))

        doc.add_heading("Trigger condition extracted from traces", level=2)
        doc.add_paragraph(str(row["trigger_condition_summary"]))

        doc.add_heading("Best repaired assertion", level=2)
        doc.add_paragraph(str(row["best_repaired_assertion"]))

        doc.add_heading("Outcome snapshot", level=2)
        outcome = pd.DataFrame(
            [
                ["original_correct_pass", row["original_correct_pass"]],
                ["repaired_correct_pass", row["repaired_correct_pass"]],
                ["original_fail_on_buggy", row["original_fail_on_buggy"]],
                ["repaired_fail_on_buggy", row["repaired_fail_on_buggy"]],
                ["original_antecedent_hit", row["original_antecedent_hit"]],
                ["repaired_antecedent_hit", row["repaired_antecedent_hit"]],
                ["correct_pass_preserved", row["correct_pass_preserved"]],
                ["fail_on_buggy_improved", row["fail_on_buggy_improved"]],
                ["antecedent_hit_improved", row["antecedent_hit_improved"]],
                ["false_positive_introduced", row["false_positive_introduced"]],
                ["heldout_failure_introduced", row["heldout_failure_introduced"]],
            ],
            columns=["metric", "value"],
        )
        add_table(doc, outcome)

        prompt_match = prompt_df[prompt_df["case_id"] == row["case_id"]]
        if not prompt_match.empty:
            doc.add_heading("Repair prompt used for LLM", level=2)
            doc.add_paragraph(str(prompt_match.iloc[0]["repair_prompt_text"]))

    out_path = OUT_DIR / "antecedent_repair_prompts.docx"
    doc.save(out_path)
    print(out_path)


if __name__ == "__main__":
    main()
