#!/usr/bin/env python3
import csv
import json
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
OUT_DOCX = ROOT / "AssertionForge_Deliverables_20260530.docx"


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def set_cell_text(cell, text, bold=False, size=9, color=None):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    if color:
        run.font.color.rgb = RGBColor(*color)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def shade_cell(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_width(cell, inches):
    cell.width = Inches(inches)
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:type"), "dxa")
    tc_w.set(qn("w:w"), str(int(inches * 1440)))


def style_document(doc: Document):
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.2

    for style_name, size, color in [
        ("Heading 1", 16, RGBColor(46, 116, 181)),
        ("Heading 2", 13, RGBColor(46, 116, 181)),
        ("Heading 3", 12, RGBColor(31, 77, 120)),
    ]:
        style = styles[style_name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color


def add_title(doc: Document, title: str, subtitle: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(title)
    run.bold = True
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    run.font.size = Pt(20)
    run.font.color.rgb = RGBColor(11, 37, 69)

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(14)
    run2 = p2.add_run(subtitle)
    run2.italic = True
    run2.font.name = "Calibri"
    run2._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    run2._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    run2.font.size = Pt(10)
    run2.font.color.rgb = RGBColor(89, 89, 89)


def add_key_value_table(doc: Document, rows, widths):
    table = doc.add_table(rows=1, cols=len(rows[0]))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for idx, text in enumerate(rows[0]):
        set_cell_text(hdr[idx], text, bold=True, size=9)
        shade_cell(hdr[idx], "E8EEF5")
        set_cell_width(hdr[idx], widths[idx])
    set_repeat_table_header(table.rows[0])

    for row_data in rows[1:]:
        row = table.add_row().cells
        for idx, text in enumerate(row_data):
            set_cell_text(row[idx], text, size=9)
            set_cell_width(row[idx], widths[idx])
    doc.add_paragraph()


def add_deliverable_index(doc: Document):
    doc.add_heading("Deliverables Overview", level=1)
    rows = [
        ["No.", "Item", "Current Deliverable"],
        ["1", "10-case manual golden assertion table", "MANUAL_GOLDEN_SVA_TABLE.md"],
        ["2", "New automatic evaluation script", "evaluate_generated_sva_v2.py"],
        ["3", "Good/bad waveform divergence summary script", "summarize_trace_divergence.py"],
        ["4", "SVA static filter script", "sva_static_filter.py"],
        ["5", "Full rerun experiment results", "strict_eval_report_rerun.csv"],
        ["6", "Four-method summary comparison", "strict_eval_comparison_rerun_by_method.csv/.md"],
        ["7", "Best assertion per case", "BEST_ASSERTION_PER_CASE.md / best_assertion_per_case.csv"],
    ]
    add_key_value_table(doc, rows, [0.45, 2.95, 3.1])


def add_manual_table(doc: Document, cases):
    doc.add_heading("1. Manual Golden Assertion Table", level=1)
    doc.add_paragraph(
        "This section captures the manual reference assertion for all 10 RTL bug cases, "
        "including expected behavior, first divergence cycle, and temporal interpretation."
    )
    rows = [[
        "Case", "Bug Type", "Golden SVA", "Expected Behavior",
        "First Div.", "Relevant Signals", "Temporal Type",
    ]]
    for case in cases:
        golden = case["golden_sva"]
        rows.append([
            case["name"],
            case["bug_type"],
            golden["sva"],
            golden["expected_behavior"],
            golden["first_divergence_cycle"],
            ", ".join(golden["relevant_signals"]),
            golden["temporal_type"],
        ])
    add_key_value_table(doc, rows, [1.15, 1.0, 2.35, 2.3, 0.65, 1.45, 1.6])


def add_script_section(doc: Document):
    doc.add_heading("2-4. Script Deliverables", level=1)
    doc.add_paragraph(
        "The following scripts remain source-code artifacts and are referenced here in document form "
        "for packaging and archival."
    )
    rows = [
        ["Script", "Purpose", "Path"],
        [
            "evaluate_generated_sva_v2.py",
            "Runs strict evaluation and regenerates document/table deliverables from the rerun report.",
            str(ROOT / "evaluate_generated_sva_v2.py"),
        ],
        [
            "summarize_trace_divergence.py",
            "Extracts first good/bad waveform divergence and emits compact case-level summaries.",
            str(ROOT / "summarize_trace_divergence.py"),
        ],
        [
            "sva_static_filter.py",
            "Rejects malformed or semantically weak SVA candidates before simulation evaluation.",
            str(ROOT / "sva_static_filter.py"),
        ],
    ]
    add_key_value_table(doc, rows, [1.6, 2.7, 2.2])


def add_method_summary(doc: Document, method_rows):
    doc.add_heading("6. Four-Method Summary Comparison", level=1)
    doc.add_paragraph(
        "The summary below uses deduplicated assertion text per method and counts success by case rather than by repeated candidate rows."
    )
    rows = [[
        "Method", "Raw Rows", "Distinct Assertions", "Cases", "Syntax Pass", "Correct Pass",
        "Buggy Fail", "Non-vacuous", "Triggered", "Strict Success Assertions", "Success Cases",
    ]]
    for row in method_rows:
        rows.append([
            row["label"],
            row["raw_rows"],
            row["num_rows"],
            row["num_cases"],
            row["syntax_pass"],
            row["correct_pass"],
            row["buggy_fail"],
            row["non_vacuous"],
            row["antecedent_triggered"],
            row["strict_success_assertions"],
            row["success_cases"],
        ])
    add_key_value_table(
        doc,
        rows,
        [1.55, 0.65, 0.95, 0.45, 0.7, 0.7, 0.65, 0.7, 0.55, 0.95, 0.75],
    )

    doc.add_heading("Failure Type Breakdown", level=2)
    for row in method_rows:
        p = doc.add_paragraph()
        p.add_run(row["label"] + ": ").bold = True
        p.add_run(row["failure_type_counts"])


def add_best_assertions(doc: Document, best_rows):
    doc.add_heading("7. Best Assertion Per Case", level=1)
    doc.add_paragraph(
        "For each case, the selected candidate is chosen by ranking `strict_success`, `syntax_pass`, "
        "`pass_on_correct`, `fail_on_buggy`, `non_vacuous`, `antecedent_triggered`, and then method richness."
    )
    rows = [[
        "Case", "Bug Type", "Best Method", "Cand.", "Failure Type",
        "Correct Pass", "Buggy Fail", "Assertion",
    ]]
    for row in best_rows:
        rows.append([
            row["case_name"],
            row["bug_type"],
            row["method_label"],
            row["candidate_index"],
            row["failure_type"],
            row["pass_on_correct"],
            row["fail_on_buggy"],
            row["assertion_line"],
        ])
    add_key_value_table(doc, rows, [1.2, 1.15, 1.45, 0.45, 1.2, 0.7, 0.65, 2.7])


def add_full_results_appendix(doc: Document, report_rows):
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Inches(11)
    section.page_height = Inches(8.5)
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.6)
    section.left_margin = Inches(0.6)
    section.right_margin = Inches(0.6)

    doc.add_heading("5. Full Rerun Experiment Result Table", level=1)
    doc.add_paragraph(
        "Appendix table covering the cleaned rerun result set after removing template garbage rows. "
        "Columns are trimmed to the evaluation dimensions most useful for review."
    )

    rows = [[
        "Case", "Method", "Cand.", "Syntax", "Correct", "Buggy",
        "Non-vac.", "Triggered", "Failure Type", "Assertion",
    ]]
    for row in report_rows:
        rows.append([
            row["case_name"],
            row["method"],
            row["candidate_index"],
            row["syntax_pass"],
            row["pass_on_correct"],
            row["fail_on_buggy"],
            row["non_vacuous"],
            row["antecedent_triggered"],
            row["failure_type"],
            row["assertion_line"],
        ])
    add_key_value_table(doc, rows, [1.25, 1.05, 0.45, 0.45, 0.5, 0.45, 0.6, 0.6, 1.25, 3.9])


def main():
    cases = json.loads((ROOT / "case_manifest.json").read_text(encoding="utf-8"))["cases"]
    method_rows = read_csv(ROOT / "strict_eval_comparison_rerun_by_method.csv")
    best_rows = read_csv(ROOT / "best_assertion_per_case.csv")
    report_rows = read_csv(ROOT / "strict_eval_report_rerun.csv")

    doc = Document()
    style_document(doc)
    add_title(
        doc,
        "AssertionForge Deliverables",
        "DOCX packaging of the 10-case manual assertions, scripts, rerun results, and summary tables",
    )
    add_deliverable_index(doc)
    add_manual_table(doc, cases)
    add_script_section(doc)
    add_method_summary(doc, method_rows)
    add_best_assertions(doc, best_rows)
    add_full_results_appendix(doc, report_rows)
    doc.save(OUT_DOCX)
    print(f"[DONE] Wrote {OUT_DOCX}")


if __name__ == "__main__":
    main()
