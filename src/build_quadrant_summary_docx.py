from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DATA_DIR = ROOT / "outputs" / THREAD_ID / "quadrant_analysis_data"
OUTPUT_DOCX = ROOT / "outputs" / THREAD_ID / "四象限总结一页.docx"

SUMMARY_JSON = DATA_DIR / "quadrant_summary.json"
OVERALL_CSV = DATA_DIR / "quadrant_overall_matrix.csv"
BUG_CLASS_CSV = DATA_DIR / "quadrant_by_bug_class_matrix.csv"


BLUE = RGBColor(46, 116, 181)
DARK = RGBColor(31, 77, 120)
BLACK = RGBColor(0, 0, 0)
GRAY = RGBColor(96, 96, 96)


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


def add_para(doc, text="", *, size=11, bold=False, color=BLACK, align=WD_ALIGN_PARAGRAPH.LEFT, after=6, before=0):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.10
    if text:
        run = p.add_run(text)
        set_run_font(run, size=size, color=color, bold=bold)
    return p


def add_label_value(doc, label, value):
    p = add_para(doc, "", size=11, after=4)
    r1 = p.add_run(label)
    set_run_font(r1, size=11, color=DARK, bold=True)
    r2 = p.add_run(value)
    set_run_font(r2, size=11, color=BLACK)
    return p


def main():
    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    overall_df = pd.read_csv(OVERALL_CSV)
    bug_df = pd.read_csv(BUG_CLASS_CSV)

    doc = Document()
    section = doc.sections[0]
    section.start_type = WD_SECTION.NEW_PAGE
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

    # memo_masthead-inspired opening block
    p = add_para(doc, "四象限分析总结", size=20, bold=True, color=BLACK, after=4)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    add_para(
        doc,
        "对象：去重后的 clean assertion（23 cases / 191 assertions）",
        size=11.5,
        color=GRAY,
        after=10,
    )

    add_label_value(
        doc,
        "总体结论：",
        "四种方法里，“太弱”都是最大象限；说明大部分断言能在 correct 上通过，但抓不住 buggy 行为。",
    )

    method_lines = []
    for _, row in overall_df.iterrows():
        method_label = row["method_label"]
        success = int(row["真成功"])
        weak = int(row["太弱"])
        strong = int(row["太强"])
        invalid = int(row["无效"])
        total = int(row["total_assertions"])
        success_share = float(row["真成功_share"]) * 100.0
        method_lines.append(
            f"{method_label}: 真成功 {success}, 太弱 {weak}, 太强 {strong}, 无效 {invalid}（总计 {total}；真成功占比 {success_share:.1f}%）"
        )

    add_label_value(doc, "四种方法：", method_lines[0])
    for extra in method_lines[1:]:
        add_para(doc, extra, size=11, after=3)

    comb = bug_df[bug_df["bug_class"] == "combination_same_cycle"].copy()
    temp = bug_df[bug_df["bug_class"] == "temporal_cross_cycle"].copy()
    comb_best = comb.sort_values(["真成功", "太弱"], ascending=[False, True]).iloc[0]
    temp_best = temp.sort_values(["真成功", "太弱"], ascending=[False, True]).iloc[0]

    add_label_value(
        doc,
        "按 bug_class 看：",
        f"combination_same_cycle 中，{comb_best['method_label']} 的真成功数最高（{int(comb_best['真成功'])}）。",
    )
    add_para(
        doc,
        f"temporal_cross_cycle 中，{temp_best['method_label']} 的真成功数最高（{int(temp_best['真成功'])}）；但 raw trace 的太弱数最低（{int(temp[temp['method_label'] == 'spec + RTL + raw trace']['太弱'].iloc[0])}）。",
        size=11,
        after=4,
    )

    add_label_value(
        doc,
        "case 级解释规则：",
        summary["primary_rule"],
    )
    add_para(
        doc,
        f"补充：92 个 case-method 组合里，82 个有 clean assertion，10 个没有；其中 35 个 case-method 同时落入多个象限，因此 by_case 里同时保留了 primary_quadrant 和 quadrants_seen。",
        size=10.5,
        color=GRAY,
        after=0,
    )

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.paragraph_format.space_before = Pt(0)
    footer.paragraph_format.space_after = Pt(0)
    run = footer.add_run("Quadrant summary | real admitted clean assertions")
    set_run_font(run, size=9, color=GRAY)

    doc.save(OUTPUT_DOCX)
    print(OUTPUT_DOCX)


if __name__ == "__main__":
    main()
