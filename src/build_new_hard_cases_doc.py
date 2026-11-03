from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DATA_PATH = ROOT / "outputs" / THREAD_ID / "new_hard_cases_data" / "hard_cases_design_master.json"
OUT_DOC = ROOT / "outputs" / THREAD_ID / "每个case一页说明.docx"

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
    normal.font.size = Pt(10.5)


def add_para(
    doc: Document,
    text="",
    *,
    size=10.5,
    bold=False,
    color=BLACK,
    after=4,
    before=0,
    align=WD_ALIGN_PARAGRAPH.LEFT,
):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.12
    if text:
        r = p.add_run(text)
        set_run_font(r, size=size, color=color, bold=bold)
    return p


def add_label_value(doc: Document, label: str, value: str, *, size=10.2, after=3):
    p = add_para(doc, "", size=size, after=after)
    r1 = p.add_run(label)
    set_run_font(r1, size=size, color=DARK, bold=True)
    r2 = p.add_run(value)
    set_run_font(r2, size=size, color=BLACK)
    return p


def main():
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]

    doc = Document()
    style_doc(doc)

    for idx, case in enumerate(cases):
        add_para(doc, case["case_id"], size=16, bold=True, color=BLACK, after=2)
        add_para(
            doc,
            f"Group {case['group_id']} | {case['group_theme']} | module={case['module']}",
            size=10.0,
            color=GRAY,
            after=6,
        )

        add_label_value(
            doc,
            "Meta: ",
            f"bug_class={case['bug_class']} | temporal_type={case['temporal_type']} | "
            f"expected_trace_effect={case['expected_trace_effect']} | overfit_lure_present={case['overfit_lure_present']}",
            after=4,
        )
        add_label_value(doc, "Spec: ", case["spec"], after=4)
        add_label_value(doc, "Correct RTL sketch: ", case["correct_rtl"], after=4)
        add_label_value(doc, "Buggy RTL sketch: ", case["buggy_rtl"], after=4)
        add_label_value(doc, "Bug description: ", case["bug_description"], after=4)
        add_label_value(doc, "Seen good trace: ", case["seen_good_trace"], after=3)
        add_label_value(doc, "Seen bad trace: ", case["seen_bad_trace"], after=3)
        add_label_value(doc, "Held-out good trace: ", case["heldout_good_trace"], after=3)
        add_label_value(doc, "Held-out bad trace: ", case["heldout_bad_trace"], after=4)
        add_label_value(doc, "Golden SVA: ", case["golden_sva"], after=4)
        add_label_value(doc, "Golden self-check result: ", case["golden_self_check_result"], after=4)
        add_label_value(doc, "Why hard: ", case["why_hard"], after=2)

        if idx < len(cases) - 1:
            p = doc.add_paragraph()
            r = p.add_run()
            r.add_break(WD_BREAK.PAGE)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("每个case一页说明")
    set_run_font(r, size=9, color=GRAY)

    doc.save(OUT_DOC)
    print(OUT_DOC)


if __name__ == "__main__":
    main()
