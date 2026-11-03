from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DATA_DIR = ROOT / "outputs" / THREAD_ID / "raw_vs_summary_data"
OUT_DOC = ROOT / "outputs" / THREAD_ID / "raw_vs_summary_case_notes.docx"

BLACK = RGBColor(0, 0, 0)
DARK = RGBColor(31, 77, 120)
GRAY = RGBColor(96, 96, 96)

ORDER = ["raw trace 更好", "trace summary 更好", "两者都不好", "两者表现相反"]


def set_run_font(run, name="Calibri", size=None, color=None, bold=None, italic=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:ascii"), name)
    run._element.rPr.rFonts.set(qn("w:hAnsi"), name)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def style_doc(doc: Document):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    normal.font.size = Pt(11)


def add_para(
    doc: Document,
    text="",
    *,
    size=11,
    bold=False,
    color=BLACK,
    after=6,
    before=0,
    align=WD_ALIGN_PARAGRAPH.LEFT,
):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.10
    if text:
        r = p.add_run(text)
        set_run_font(r, size=size, color=color, bold=bold)
    return p


def add_label_value(doc: Document, label: str, value: str):
    p = add_para(doc, "", after=4)
    r1 = p.add_run(label)
    set_run_font(r1, size=11, color=DARK, bold=True)
    r2 = p.add_run(value)
    set_run_font(r2, size=11, color=BLACK)
    return p


def main():
    summary = json.loads((DATA_DIR / "raw_vs_summary_summary.json").read_text(encoding="utf-8"))
    questions = pd.read_csv(DATA_DIR / "raw_vs_summary_questions.csv")
    cases = pd.read_csv(DATA_DIR / "raw_vs_summary_case_comparison.csv")
    conclusion_counts = pd.read_csv(DATA_DIR / "raw_vs_summary_conclusion_counts.csv")

    doc = Document()
    style_doc(doc)
    add_para(doc, "Raw trace vs trace summary case notes", size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "基于 clean master 中 raw trace 与 trace summary 两条方法线的直接比较，回答 hardcoding、关键时序信息丢失、保守性和 held-out 泛化这几个问题，并为每个 case 给出一句结论。",
        size=11.5,
        color=GRAY,
        after=10,
    )

    add_label_value(
        doc,
        "比较范围：",
        f"{summary['union_case_count']} 个 union case，其中 {summary['overlap_case_count']} 个 case 同时拥有 raw / summary 两条方法线；"
        f"raw-only={summary['raw_only_case_count']}，summary-only={summary['summary_only_case_count']}。",
    )
    if summary["raw_only_cases"]:
        add_label_value(doc, "raw-only cases：", "，".join(summary["raw_only_cases"]))
    if summary["summary_only_cases"]:
        add_label_value(doc, "summary-only cases：", "，".join(summary["summary_only_cases"]))

    add_para(doc, "五个核心问题", size=12.5, bold=True, color=DARK, after=4, before=10)
    for row in questions.itertuples():
        add_para(doc, str(row.question), size=11.2, bold=True, color=DARK, after=2, before=6)
        add_para(doc, str(row.short_answer), size=10.8, after=2)
        add_para(doc, str(row.evidence), size=10.2, color=GRAY, after=4)

    add_para(doc, "Case 结论分布", size=12.5, bold=True, color=DARK, after=4, before=10)
    for row in conclusion_counts.itertuples():
        add_para(doc, f"{row.case_conclusion}：{int(row.case_count)} 个 case", size=10.8, after=2)

    for label in ORDER:
        sub = cases[cases["case_conclusion"] == label].copy()
        if sub.empty:
            continue
        add_para(doc, label, size=12.5, bold=True, color=DARK, after=4, before=12)
        for row in sub.sort_values("case_id").itertuples():
            add_para(doc, str(row.case_id), size=11.0, bold=True, color=DARK, after=1, before=5)
            add_para(
                doc,
                f"bug_class={row.bug_class} | raw_score={float(row.raw_score):.3f} | summary_score={float(row.summary_score):.3f}",
                size=9.8,
                color=GRAY,
                after=2,
            )
            add_para(doc, str(row.case_note), size=10.5, after=4)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("Raw trace vs trace summary case notes")
    set_run_font(r, size=9, color=GRAY)

    doc.save(OUT_DOC)
    print(OUT_DOC)


if __name__ == "__main__":
    main()
