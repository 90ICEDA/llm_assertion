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
DATA_DIR = ROOT / "outputs" / THREAD_ID / "vacuity_analysis_data"
OUT_ANT = ROOT / "outputs" / THREAD_ID / "antecedent_not_triggered_cases.docx"
OUT_REP = ROOT / "outputs" / THREAD_ID / "每个case代表性失败例子.docx"


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


def add_para(doc: Document, text="", *, size=11, bold=False, color=BLACK, after=6, before=0, align=WD_ALIGN_PARAGRAPH.LEFT):
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


def trim_text(text: str, limit: int = 180) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_antecedent_doc():
    summary = json.loads((DATA_DIR / "vacuity_summary.json").read_text(encoding="utf-8"))
    method_df = pd.read_csv(DATA_DIR / "vacuity_method_summary.csv")
    case_df = pd.read_csv(DATA_DIR / "vacuity_case_summary.csv")
    ant_zero_df = pd.read_csv(DATA_DIR / "antecedent_zero_summary.csv")
    rep_vac_df = pd.read_csv(DATA_DIR / "representative_failures_vacuity_priority.csv")

    doc = Document()
    style_doc(doc)

    add_para(doc, "Antecedent Not Triggered Cases", size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "vacuity 专项说明：聚焦 buggy trace 上 antecedent 根本没触发的 failure。",
        size=11.5,
        color=GRAY,
        after=10,
    )

    add_label_value(
        doc,
        "核心结果：",
        f"102 条 fail_on_buggy=0 的 clean assertions 中，有 {summary['buggy_antecedent_zero_count']} 条在 buggy trace 上 antecedent_hit=0，覆盖 {summary['buggy_antecedent_zero_case_count']} 个 case。",
    )

    top_method = method_df.sort_values("buggy_antecedent_zero_count", ascending=False).iloc[0]
    add_label_value(
        doc,
        "方法层面：",
        f"{top_method['method_label']} 的 antecedent_hit_buggy=0 数量最多，为 {int(top_method['buggy_antecedent_zero_count'])} 条；四种方法里 vacuous_share 都在 73% 以上。",
    )

    top_cases = case_df.sort_values("buggy_antecedent_zero_count", ascending=False).head(5)
    add_para(doc, "高频 antecedent_not_triggered cases：", size=11, bold=True, color=DARK, after=4, before=8)
    for _, row in top_cases.iterrows():
        add_para(
            doc,
            f"- {row['case_id']}: buggy antecedent_hit=0 共 {int(row['buggy_antecedent_zero_count'])} 条，fail assertions 共 {int(row['fail_assertion_count'])} 条。",
            size=10.5,
            after=2,
        )

    add_para(doc, "每个 case 的代表性 vacuous 例子：", size=11, bold=True, color=DARK, after=6, before=10)
    for _, row in rep_vac_df.sort_values("case_id").iterrows():
        case_id = row["case_id"]
        method = row["method_label"]
        p = add_para(doc, "", size=10.5, after=1)
        r1 = p.add_run(f"{case_id} ({method})：")
        set_run_font(r1, size=10.5, color=DARK, bold=True)
        r2 = p.add_run(trim_text(str(row["representative_explanation"]), 220))
        set_run_font(r2, size=10.5, color=BLACK)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("Vacuity analysis | antecedent not triggered")
    set_run_font(r, size=9, color=GRAY)

    doc.save(OUT_ANT)


def build_rep_doc():
    rep_df = pd.read_csv(DATA_DIR / "representative_failures_diagnostic_priority.csv")
    summary = json.loads((DATA_DIR / "vacuity_summary.json").read_text(encoding="utf-8"))

    doc = Document()
    style_doc(doc)

    add_para(doc, "每个 case 代表性失败例子", size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "选择规则：优先挑更有诊断价值的 failure mode（trace_overfit > too_weak > non_vacuous_miss > unsupported_analysis > vacuous_miss）。",
        size=11.0,
        color=GRAY,
        after=10,
    )

    add_label_value(
        doc,
        "分布概览：",
        f"19 个 case 至少有 1 条 fail_on_buggy=0 的 clean assertion；其中 vacuous_miss 80 条、too_weak 9 条、trace_overfit 5 条、unsupported_analysis 4 条、non_vacuous_miss 4 条。",
    )

    for _, row in rep_df.sort_values("case_id").iterrows():
        add_para(doc, row["case_id"], size=12, bold=True, color=DARK, after=3, before=10)
        add_para(
            doc,
            f"module={row['module']} | bug_class={row['bug_class']} | method={row['method_label']} | bucket={row['paper_bucket']}",
            size=9.8,
            color=GRAY,
            after=3,
        )
        add_para(doc, f"Assertion: {trim_text(str(row['assertion_text']), 260)}", size=10.2, after=2)
        add_para(doc, trim_text(str(row["representative_explanation"]), 320), size=10.5, after=4)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("Vacuity analysis | representative failures")
    set_run_font(r, size=9, color=GRAY)

    doc.save(OUT_REP)


if __name__ == "__main__":
    build_antecedent_doc()
    build_rep_doc()
    print(OUT_ANT)
    print(OUT_REP)
