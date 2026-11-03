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
DATA_DIR = ROOT / "outputs" / THREAD_ID / "trace_tradeoff_data"
OUT_CASE = ROOT / "outputs" / THREAD_ID / "trace_tradeoff_by_case.docx"
OUT_SUMMARY = ROOT / "outputs" / THREAD_ID / "trace_tradeoff_summary.docx"


BLUE = RGBColor(46, 116, 181)
DARK = RGBColor(31, 77, 120)
BLACK = RGBColor(0, 0, 0)
GRAY = RGBColor(96, 96, 96)

METHOD_LABEL = {
    "spec_only": "spec only",
    "spec_plus_rtl": "spec + RTL",
    "spec_rtl_raw_trace": "spec + RTL + raw trace",
    "spec_rtl_trace_summary": "spec + RTL + trace summary",
}


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


def signed(num: int) -> str:
    return f"{num:+d}"


def build_bug_class_paragraph(row: pd.Series, contributors: pd.DataFrame) -> str:
    bug_class = row["bug_class"]
    correct_delta = int(row["correct_pass_delta"])
    fail_delta = int(row["fail_on_buggy_delta"])
    ant_delta = int(row["antecedent_hit_delta"])
    nonv_delta = int(row["non_vacuous_delta"])
    heldout_delta = int(row["heldout_success_delta"])
    overfit_delta = int(row["trace_overfit_delta"])

    parts: list[str] = []
    if correct_delta > 0 and fail_delta < 0:
        parts.append("trace summary 在这一类 bug 上更保守：correct_pass 上升，但 fail_on_buggy 下降")
    elif fail_delta > 0 and correct_delta < 0:
        parts.append("trace summary 在这一类 bug 上更激进：fail_on_buggy 上升，但 correct_pass 下降")
    elif correct_delta > 0 and fail_delta == 0:
        parts.append("trace summary 主要提升了 correct 侧稳定性，但没有带来额外 bug 检测增益")
    elif fail_delta > 0 and correct_delta == 0:
        parts.append("trace summary 主要提升了 bug 检测，而且没有伤到 correct 侧")
    elif fail_delta == 0 and correct_delta == 0:
        parts.append("trace summary 与 spec + RTL 在最核心的 correct/fail 维度上基本持平")
    else:
        parts.append("trace summary 的影响比较混合，既有收益也有损失")

    if ant_delta > 0:
        parts.append(f"buggy 侧 antecedent_hit {signed(ant_delta)}，说明摘要帮助模型更容易命中触发条件")
    elif ant_delta < 0:
        parts.append(f"buggy 侧 antecedent_hit {signed(ant_delta)}，说明摘要压缩后丢掉了部分触发线索")

    if nonv_delta > 0:
        parts.append(f"non_vacuous {signed(nonv_delta)}，这部分增益不是纯粹 vacuous hit")
    elif nonv_delta < 0:
        parts.append(f"non_vacuous {signed(nonv_delta)}，说明摘要让部分断言退化成更弱的 buggy-side 约束")

    if heldout_delta > 0:
        parts.append(f"heldout_success {signed(heldout_delta)}，泛化更好")
    elif heldout_delta < 0:
        parts.append(f"heldout_success {signed(heldout_delta)}，泛化更差")

    if overfit_delta > 0:
        parts.append(f"trace_overfit {signed(overfit_delta)}，提示摘要也可能把模型推向 trace-specific 规则")

    sub = contributors[(contributors["bug_class"] == bug_class) & (contributors["metric"] == "fail_on_buggy")]
    pos = sub[sub["direction"] == "positive"]["case_id"].tolist()[:3]
    neg = sub[sub["direction"] == "negative"]["case_id"].tolist()[:3]
    if pos:
        parts.append(f"主要正向 case 包括 {', '.join(pos)}")
    if neg:
        parts.append(f"主要负向 case 包括 {', '.join(neg)}")

    return "；".join(parts) + "。"


def build_summary_doc():
    summary = json.loads((DATA_DIR / "trace_tradeoff_summary.json").read_text(encoding="utf-8"))
    overall_df = pd.read_csv(DATA_DIR / "tradeoff_overall_metric_delta.csv")
    bug_signal_df = pd.read_csv(DATA_DIR / "tradeoff_bug_class_signals.csv")
    contributors_df = pd.read_csv(DATA_DIR / "tradeoff_case_contributors.csv")

    doc = Document()
    style_doc(doc)

    add_para(doc, "Trace tradeoff summary", size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "比较对象：spec + RTL 基线 vs. spec + RTL + trace summary；同时补充 raw trace 对照，用于识别过拟合与信息损失。",
        size=11.5,
        color=GRAY,
        after=10,
    )

    overall_lookup = overall_df.set_index("metric")
    add_label_value(
        doc,
        "总体结论：",
        "相比 spec + RTL，trace summary 的总体变化是 "
        + ", ".join(
            [
                f"{metric} {signed(int(overall_lookup.loc[metric, 'delta_summary_minus_spec_plus_rtl']))}"
                for metric in [
                    "correct_pass",
                    "fail_on_buggy",
                    "antecedent_hit",
                    "non_vacuous",
                    "heldout_success",
                    "trace_overfit",
                ]
            ]
        )
        + "。",
    )

    classes_up_down = summary["bug_classes_correct_up_fail_down"]
    classes_down_up = summary["bug_classes_fail_up_correct_down"]
    add_label_value(
        doc,
        "按 bug_class 看关键信号：",
        f"correct_pass 上升但 fail_on_buggy 下降的 bug_class：{', '.join(classes_up_down) if classes_up_down else '无'}；"
        f"fail_on_buggy 上升但 correct_pass 下降的 bug_class：{', '.join(classes_down_up) if classes_down_up else '无'}。",
    )

    add_label_value(
        doc,
        "raw trace 过拟合更重的 case：",
        ", ".join(summary["raw_trace_more_overfit_cases"]) if summary["raw_trace_more_overfit_cases"] else "无",
    )
    add_label_value(
        doc,
        "trace summary 丢失有用信息的 case：",
        ", ".join(summary["summary_lost_useful_info_cases"]) if summary["summary_lost_useful_info_cases"] else "无",
    )

    add_para(doc, "各 bug_class 解释", size=12, bold=True, color=DARK, after=5, before=10)
    for _idx, row in bug_signal_df.iterrows():
        add_para(doc, str(row["bug_class"]), size=11.5, bold=True, color=DARK, after=2, before=8)
        add_para(doc, build_bug_class_paragraph(row, contributors_df), size=10.8, after=3)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("Trace tradeoff summary")
    set_run_font(r, size=9, color=GRAY)

    doc.save(OUT_SUMMARY)


def build_case_doc():
    case_df = pd.read_csv(DATA_DIR / "tradeoff_case_delta.csv")

    doc = Document()
    style_doc(doc)

    add_para(doc, "Trace tradeoff by case", size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "每个 case 都按 trace summary 相对 spec + RTL 的差值记录；另外补充 trace summary 与 raw trace 的过拟合对照。",
        size=11.5,
        color=GRAY,
        after=10,
    )

    raw_overfit_cases = case_df[case_df["raw_trace_more_trace_overfit_than_summary"]].copy()
    literal_cases = case_df[
        (~case_df["raw_trace_more_trace_overfit_than_summary"])
        & (case_df["raw_trace_more_literal_hardcoding_than_summary"])
    ].copy()
    lost_cases = case_df[case_df["summary_lost_useful_info_vs_spec_plus_rtl"]].copy()

    add_label_value(
        doc,
        "raw trace 更容易过拟合：",
        ", ".join(raw_overfit_cases["case_id"].tolist()) if not raw_overfit_cases.empty else "无",
    )
    if not literal_cases.empty:
        add_label_value(
            doc,
            "raw trace 还表现出更强 literal hardcoding 的 case：",
            ", ".join(literal_cases["case_id"].tolist()),
        )

    add_label_value(
        doc,
        "trace summary 丢失有用信息的 case：",
        ", ".join(lost_cases["case_id"].tolist()) if not lost_cases.empty else "无",
    )

    add_para(doc, "逐 case 说明", size=12, bold=True, color=DARK, after=5, before=10)
    for _idx, row in case_df.sort_values(["bug_class", "case_id"]).iterrows():
        add_para(doc, str(row["case_id"]), size=11.5, bold=True, color=DARK, after=2, before=8)
        add_para(
            doc,
            f"bug_class={row['bug_class']} | module={row['module']} | bug_name={row['bug_name']}",
            size=9.8,
            color=GRAY,
            after=2,
        )
        add_para(
            doc,
            "vs spec + RTL: "
            f"correct_pass {signed(int(row['delta_correct_pass_vs_spec_plus_rtl']))}, "
            f"fail_on_buggy {signed(int(row['delta_fail_on_buggy_vs_spec_plus_rtl']))}, "
            f"antecedent_hit {signed(int(row['delta_antecedent_hit_vs_spec_plus_rtl']))}, "
            f"non_vacuous {signed(int(row['delta_non_vacuous_vs_spec_plus_rtl']))}, "
            f"heldout_success {signed(int(row['delta_heldout_success_vs_spec_plus_rtl']))}, "
            f"trace_overfit {signed(int(row['delta_trace_overfit_vs_spec_plus_rtl']))}.",
            size=10.2,
            after=2,
        )
        add_para(
            doc,
            "vs raw trace: "
            f"correct_pass {signed(int(row['delta_correct_pass_summary_vs_raw']))}, "
            f"fail_on_buggy {signed(int(row['delta_fail_on_buggy_summary_vs_raw']))}, "
            f"antecedent_hit {signed(int(row['delta_antecedent_hit_summary_vs_raw']))}, "
            f"heldout_success {signed(int(row['delta_heldout_success_summary_vs_raw']))}, "
            f"trace_overfit {signed(int(row['delta_trace_overfit_summary_vs_raw']))}, "
            f"literal_hardcoding {signed(int(row['delta_literal_hardcoding_summary_vs_raw']))}.",
            size=10.2,
            after=2,
        )
        add_para(doc, str(row["case_note"]), size=10.5, after=4)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("Trace tradeoff by case")
    set_run_font(r, size=9, color=GRAY)

    doc.save(OUT_CASE)


if __name__ == "__main__":
    build_summary_doc()
    build_case_doc()
    print(OUT_SUMMARY)
    print(OUT_CASE)
