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
DATA_DIR = ROOT / "outputs" / THREAD_ID / "temporal_type_analysis_data"
OUT_DOC = ROOT / "outputs" / THREAD_ID / "temporal_type_failure_examples.docx"

TEMPORAL_ORDER = [
    "multi_cycle_delay",
    "hold_until_ready",
    "stability",
    "counter_boundary",
    "fifo_boundary",
    "onehot",
    "fsm_transition",
]

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


def pct(value) -> str:
    return f"{float(value):.1%}"


def main():
    overall = pd.read_csv(DATA_DIR / "temporal_type_overall.csv")
    examples = pd.read_csv(DATA_DIR / "temporal_type_examples.csv")
    breakdown = pd.read_csv(DATA_DIR / "temporal_type_failure_breakdown.csv")
    summary = json.loads((DATA_DIR / "temporal_type_summary.json").read_text(encoding="utf-8"))

    overall = overall.set_index("temporal_type")

    doc = Document()
    style_doc(doc)

    add_para(doc, "Temporal type failure examples", size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "基于 clean master 中 191 条去重 assertion，按 temporal_type 重新观察 LLM 在 compile、正确侧通过、buggy 侧区分、vacuity、held-out 泛化和 trace overfit 上的失败模式。",
        size=11.5,
        color=GRAY,
        after=10,
    )

    add_label_value(doc, "总体范围：", f"{summary['total_cases']} 个 case，{summary['total_assertions']} 条 assertion。")
    add_label_value(
        doc,
        "bug 检测最难的 temporal_type：",
        "、".join(summary["hardest_by_fail_on_buggy_rate"]),
    )
    add_label_value(
        doc,
        "held-out 泛化最弱的 temporal_type：",
        "、".join(summary["hardest_by_heldout_success_rate"]),
    )
    add_label_value(
        doc,
        "vacuity 最严重的 temporal_type：",
        "、".join(summary["highest_vacuity_rate"]),
    )
    add_label_value(doc, "分桶说明：", summary["mapping_note"])

    for temporal_type in TEMPORAL_ORDER:
        if temporal_type not in overall.index:
            continue
        row = overall.loc[temporal_type]
        ex = examples[examples["temporal_type"] == temporal_type].iloc[0]
        top_failure = breakdown[breakdown["temporal_type"] == temporal_type].head(3)

        add_para(doc, temporal_type, size=12.5, bold=True, color=DARK, after=3, before=10)
        add_para(
            doc,
            f"cases={int(row['case_count'])}, assertions={int(row['assertion_count'])}; "
            f"compile_ok={pct(row['compile_ok_rate'])}, correct_pass={pct(row['correct_pass_rate'])}, "
            f"fail_on_buggy={pct(row['fail_on_buggy_rate'])}, antecedent_hit={pct(row['antecedent_hit_rate'])}, "
            f"vacuity={pct(row['vacuity_rate'])}, heldout_success={pct(row['heldout_success_rate'])}, "
            f"trace_overfit={pct(row['trace_overfit_rate'])}.",
            size=10.6,
            after=3,
        )

        if not top_failure.empty:
            failure_line = "；".join(
                [
                    f"{item.failure_type}={int(item.assertion_count)} ({pct(item.share_within_temporal_type_failure)})"
                    for item in top_failure.itertuples()
                ]
            )
            add_para(doc, f"主导失败模式：{failure_line}。", size=10.4, color=GRAY, after=3)

        add_para(
            doc,
            f"代表例子：{ex['case_id']} | {ex['method_label']} | failure_type={ex['failure_type']}",
            size=10.8,
            bold=True,
            color=DARK,
            after=2,
        )
        add_para(doc, f"assertion: {ex['assertion_text']}", size=10.0, color=GRAY, after=2)
        if str(ex.get("failure_reason", "")).strip():
            add_para(doc, f"failure_reason: {ex['failure_reason']}", size=10.0, color=GRAY, after=2)
        add_para(doc, str(ex["example_note"]), size=10.6, after=5)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("Temporal type failure examples")
    set_run_font(r, size=9, color=GRAY)

    doc.save(OUT_DOC)
    print(OUT_DOC)


if __name__ == "__main__":
    main()
