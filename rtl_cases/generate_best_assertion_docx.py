#!/usr/bin/env python3
import csv
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
OUT_DOCX = ROOT / "BEST_ASSERTION_PER_CASE.docx"


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def set_run_font(run, size=11, bold=False, italic=False, color=None):
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = color


def style_document(doc: Document):
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.2

    for style_name, size, color in [
        ("Heading 1", 16, RGBColor(46, 116, 181)),
        ("Heading 2", 13, RGBColor(46, 116, 181)),
    ]:
        style = doc.styles[style_name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color


def add_title(doc: Document):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run("Best Assertion Per Case")
    set_run_font(run, size=20, bold=True, color=RGBColor(11, 37, 69))

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(14)
    run2 = p2.add_run("One selected best assertion for each of the 10 RTL bug cases")
    set_run_font(run2, size=10, italic=True, color=RGBColor(89, 89, 89))


def add_case_sections(doc: Document, rows):
    for row in rows:
        doc.add_heading(row["case_name"], level=2)
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(row["bug_type"])
        set_run_font(run, size=10, italic=True, color=RGBColor(89, 89, 89))
        p_code = doc.add_paragraph()
        p_code.paragraph_format.left_indent = Inches(0.25)
        p_code.paragraph_format.space_after = Pt(12)
        run = p_code.add_run(row["assertion_line"])
        set_run_font(run, size=9)


def main():
    rows = read_csv(ROOT / "best_assertion_per_case.csv")
    doc = Document()
    style_document(doc)
    add_title(doc)
    add_case_sections(doc, rows)
    doc.save(OUT_DOCX)
    print(f"[DONE] Wrote {OUT_DOCX}")


if __name__ == "__main__":
    main()
