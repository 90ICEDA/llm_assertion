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
DATA_DIR = ROOT / "outputs" / THREAD_ID / "trace_overfit_data"
OUT_LITERAL = ROOT / "outputs" / THREAD_ID / "literal_hardcoding_examples.docx"
OUT_STRUCT = ROOT / "outputs" / THREAD_ID / "structural_overfit_examples.docx"
OUT_VAC = ROOT / "outputs" / THREAD_ID / "vacuous_overfit_examples.docx"


BLACK = RGBColor(0, 0, 0)
DARK = RGBColor(31, 77, 120)
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


def trim_text(text: str, limit: int = 260) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def clean_optional(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def build_doc(target_class: str, title: str, out_path: Path):
    summary = json.loads((DATA_DIR / "trace_overfit_summary.json").read_text(encoding="utf-8"))
    full_df = pd.read_csv(DATA_DIR / "trace_overfit_assertion_table.csv")
    examples_df = pd.read_csv(DATA_DIR / "trace_overfit_example_index.csv")

    sub = examples_df[examples_df["overfit_class"] == target_class].copy().head(6)
    count = int((full_df["overfit_class"] == target_class).sum())

    doc = Document()
    style_doc(doc)

    add_para(doc, title, size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "对象：raw trace / trace summary clean assertions；判定以 held-out 表现为主，同时保留 seen_success_strict 与 seen_plausible 两层标记。",
        size=11.5,
        color=GRAY,
        after=10,
    )

    add_label_value(doc, "该类样本数：", str(count))
    add_label_value(
        doc,
        "说明：",
        {
            "literal_overfit": "这类断言含明显字面量常数或 seen-trace 常数钉死，held-out 上因此误伤或漏检。",
            "structural_overfit": "这类断言没有明显常数硬编码，但只适配了 seen trace 的局部结构关系。",
            "vacuous_overfit": "这类断言在 seen 侧看起来还算合理，但 held-out 上 antecedent 不再触发，实际变成 vacuous。",
        }[target_class],
    )

    if target_class == "literal_overfit":
        pats = summary["pattern_totals_on_suspects"]
        add_label_value(
            doc,
            "可见字面量模式：",
            f"address={pats['specific_address_value']}, counter={pats['specific_counter_value']}, "
            f"state={pats['specific_state_encoding']}, fifo_depth={pats['specific_fifo_depth']}, "
            f"onehot={pats['specific_onehot_encoding']}, cycle={pats['specific_cycle_number']}, "
            f"seen_only_constant={pats['seen_only_constant']}。",
        )

    add_para(doc, "代表性例子", size=12, bold=True, color=DARK, after=5, before=10)
    for _, row in sub.iterrows():
        add_para(doc, str(row["case_id"]), size=11.5, bold=True, color=DARK, after=2, before=8)
        add_para(
            doc,
            f"method={row['method_label']} | bug_class={row['bug_class']} | seen_success_strict={row['seen_success_strict']} | heldout_issue={clean_optional(row.get('heldout_issue_label', '')) or 'n/a'}",
            size=9.8,
            color=GRAY,
            after=2,
        )
        constants = clean_optional(row.get("constant_tokens", ""))
        if constants:
            add_para(doc, f"Constants: {constants}", size=10, after=2)
        add_para(doc, f"Assertion: {trim_text(row['assertion_text'], 300)}", size=10.2, after=2)
        add_para(doc, trim_text(row["overfit_reason"], 320), size=10.5, after=2)
        failure_note = clean_optional(row.get("failure_reason", ""))
        if failure_note:
            add_para(doc, f"Failure note: {trim_text(failure_note, 260)}", size=10, color=GRAY, after=4)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run(title)
    set_run_font(r, size=9, color=GRAY)
    doc.save(out_path)


if __name__ == "__main__":
    build_doc("literal_overfit", "Literal hardcoding examples", OUT_LITERAL)
    build_doc("structural_overfit", "Structural overfit examples", OUT_STRUCT)
    build_doc("vacuous_overfit", "Vacuous overfit examples", OUT_VAC)
    print(OUT_LITERAL)
    print(OUT_STRUCT)
    print(OUT_VAC)
