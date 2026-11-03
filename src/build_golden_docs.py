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
DATA_DIR = ROOT / "outputs" / THREAD_ID / "golden_analysis_data"
ROOT_OUT_DIR = ROOT / "outputs" / THREAD_ID
OUT_EXPL = ROOT_OUT_DIR / "golden_natural_language_explanation.docx"
OUT_GAP = ROOT_OUT_DIR / "llm_vs_golden_gap_analysis.docx"

BLACK = RGBColor(0, 0, 0)
DARK = RGBColor(31, 77, 120)
GRAY = RGBColor(96, 96, 96)

FAILED_GOLDEN_EXPLANATIONS = {
    "case118_prim_filter_ctr_early_accept": (
        "这条 golden 在 seen good / seen buggy / held-out good 上都成立，且 held-out 上 antecedent 也能触发，"
        "但在 held-out buggy 上没有 fail。它只约束了 `filter_i` 刚进入过滤阶段的那个采样点必须 `!filter_o`，"
        "没有把“在计数器真正到阈值之前都不能提前放行”这个跨周期边界约束完整编码进去，所以会漏掉 held-out 中相位不同的提前接受。"
    ),
    "case119_prim_filter_ctr_late_accept": (
        "这条 golden 的 antecedent 写成 `thresh_i == 2'd2` 且要求 `$past(filter_i)`，明显绑定了 seen trace 的阈值和局部历史。"
        "到了 held-out trace，前件在 correct 和 buggy 上都不再触发，因此既没有 held-out antecedent hit，也不可能让 held-out buggy fail。"
        "它的问题主要是 antecedent 过窄、泛化不足，而不是 consequent 本身错误。"
    ),
    "case124_prim_fifo_clear_ignored": (
        "这条 golden 在 held-out 上仍然能命中 `clr_i && $past(clr_i)`，但 buggy 侧没有 fail，说明它观测到的"
        " `empty_o && depth_o == 3'd0` 只是清零后的表面输出状态，没有真正约束“FIFO 指针被复位、后续边界行为恢复一致”。"
        "对于“clear pulse does not reset FIFO pointers”这类 bug，只看 empty/depth 可能不足以区分正确实现和指针未清零的实现。"
    ),
    "case126_prim_regwe_enable_gap": (
        "这条 golden 把 onehot 条件写死为 `oh_i == 4'b0100` 且 `$past(oh_i) == 4'b0100`，本质上只覆盖了 seen trace 里的某一个具体 bit。"
        "一旦 held-out trace 换成别的 onehot 位置，antecedent 在 correct 和 buggy 上都不触发，最终表现为 held-out antecedent miss 与 held-out buggy miss。"
        "它更像示例特化检查，而不是可泛化的 enable-mismatch golden。"
    ),
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


def failed_golden_note(case_id: str, fallback: str = "") -> str:
    return FAILED_GOLDEN_EXPLANATIONS.get(case_id, fallback)


def build_explanation_doc():
    df = pd.read_csv(DATA_DIR / "golden_explanations.csv")
    full_df = pd.read_csv(DATA_DIR / "golden_selfcheck_full.csv")
    failed_df = full_df[full_df["strict_check_all_true"] != True].copy()
    failed_case_ids = set(failed_df["case_id"].astype(str))

    doc = Document()
    style_doc(doc)
    add_para(doc, "Golden natural language explanation", size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "逐条复查 30 条 golden assertion，并给出一句面向设计意图的自然语言解释。",
        size=11.5,
        color=GRAY,
        after=10,
    )

    add_para(doc, "严格复查未通过的 4 条 golden", size=12, bold=True, color=DARK, after=5, before=8)
    add_para(
        doc,
        "这 4 条都通过了 compile / seen good / seen buggy 的基本检查，但没有满足全部 held-out 条件，因此不能再视为 fully robust golden。",
        size=10.5,
        color=GRAY,
        after=6,
    )
    for _, row in failed_df.sort_values("case_id").iterrows():
        add_para(doc, str(row["case_id"]), size=11.3, bold=True, color=DARK, after=2, before=6)
        add_para(
            doc,
            f"failure_reason={row['failure_reason']} | temporal_type={row['temporal_type']} | bug_name={row['bug_name']}",
            size=9.8,
            color=GRAY,
            after=2,
        )
        add_para(doc, failed_golden_note(str(row["case_id"]), str(row["natural_language_intent"])), size=10.3, after=4)

    for _, row in df.sort_values("case_id").iterrows():
        add_para(doc, str(row["case_id"]), size=11.5, bold=True, color=DARK, after=2, before=8)
        add_para(
            doc,
            f"module={row['module']} | bug_class={row['bug_class']} | temporal_type={row['temporal_type']}",
            size=9.8,
            color=GRAY,
            after=2,
        )
        add_para(doc, str(row["natural_language_intent"]), size=10.5, after=4)
        if row["case_id"] in failed_case_ids:
            add_para(doc, f"严格复查说明：{failed_golden_note(str(row['case_id']))}", size=10.0, color=GRAY, after=4)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("Golden natural language explanation")
    set_run_font(r, size=9, color=GRAY)
    doc.save(OUT_EXPL)


def build_gap_doc():
    summary = json.loads((DATA_DIR / "golden_summary.json").read_text(encoding="utf-8"))
    temporal_df = pd.read_csv(DATA_DIR / "golden_temporal_type_summary.csv")
    full_df = pd.read_csv(DATA_DIR / "golden_selfcheck_full.csv")
    failed_df = full_df[full_df["strict_check_all_true"] != True].copy()

    doc = Document()
    style_doc(doc)
    add_para(doc, "LLM vs golden gap analysis", size=20, bold=True, color=BLACK, after=4)
    add_para(
        doc,
        "比较对象是 30 条 golden assertion，以及 clean master 中满足同等严格条件的 LLM assertions。",
        size=11.5,
        color=GRAY,
        after=10,
    )

    add_label_value(
        doc,
        "golden 自检结果：",
        f"{summary['strict_golden_pass_count']} / {summary['golden_case_count']} 条 golden 通过严格 held-out-inclusive 复查。",
    )
    add_label_value(
        doc,
        "严格复查未通过的 golden：",
        ", ".join(summary["strict_golden_fail_cases"]) if summary["strict_golden_fail_cases"] else "无",
    )
    add_label_value(
        doc,
        "LLM robust success 覆盖：",
        f"{summary['llm_robust_success_case_count']} / {summary['golden_case_count']} 个 golden case 至少被一条 LLM assertion 达到同等严格条件。",
    )
    add_label_value(
        doc,
        "clean master 缺失的 case：",
        ", ".join(summary["llm_missing_cases"]) if summary["llm_missing_cases"] else "无",
    )

    add_para(doc, "4 条失败 golden 的复查说明", size=12, bold=True, color=DARK, after=5, before=10)
    for _, row in failed_df.sort_values("case_id").iterrows():
        add_para(doc, str(row["case_id"]), size=11.2, bold=True, color=DARK, after=2, before=6)
        add_para(
            doc,
            f"failure_reason={row['failure_reason']} | heldout_correct_pass={row['heldout_correct_pass']} | "
            f"heldout_buggy_fail={row['heldout_buggy_fail']} | heldout_antecedent_hit={row['heldout_antecedent_hit']}",
            size=9.9,
            color=GRAY,
            after=2,
        )
        add_para(doc, failed_golden_note(str(row["case_id"])), size=10.3, after=4)

    add_para(doc, "按 temporal_type 看最难点", size=12, bold=True, color=DARK, after=5, before=10)
    sort_cols = ["llm_success_rate_vs_strict_goldens", "gap_vs_strict_goldens", "golden_case_count"]
    for _, row in temporal_df.sort_values(sort_cols, ascending=[True, False, False]).iterrows():
        add_para(doc, str(row["temporal_type"]), size=11.5, bold=True, color=DARK, after=2, before=8)
        add_para(
            doc,
            f"golden={int(row['golden_case_count'])}, strict_golden={int(row['strict_golden_pass_count'])}, "
            f"LLM robust success={int(row['any_llm_robust_success_case_count'])}, "
            f"gap_vs_strict={int(row['gap_vs_strict_goldens'])}, "
            f"success_rate_vs_strict={float(row['llm_success_rate_vs_strict_goldens']):.1%}.",
            size=10.4,
            after=2,
        )
        add_para(
            doc,
            f"method coverage: spec only={int(row['spec_only_success_case_count'])}, "
            f"spec+RTL={int(row['spec_plus_rtl_success_case_count'])}, "
            f"raw trace={int(row['spec_rtl_raw_trace_success_case_count'])}, "
            f"trace summary={int(row['spec_rtl_trace_summary_success_case_count'])}.",
            size=10.2,
            color=GRAY,
            after=4,
        )

    add_para(doc, "代表性 gap cases", size=12, bold=True, color=DARK, after=5, before=10)
    hard_cases = full_df[(full_df["strict_check_all_true"]) & (~full_df["any_llm_robust_success"])].copy()
    for _, row in hard_cases.sort_values(["temporal_type", "case_id"]).head(12).iterrows():
        add_para(doc, str(row["case_id"]), size=11.2, bold=True, color=DARK, after=2, before=6)
        add_para(
            doc,
            f"temporal_type={row['temporal_type']} | bug_class={row['bug_class']} | golden_intent={row['natural_language_intent']}",
            size=10.0,
            after=3,
        )

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer.add_run("LLM vs golden gap analysis")
    set_run_font(r, size=9, color=GRAY)
    doc.save(OUT_GAP)


if __name__ == "__main__":
    build_explanation_doc()
    build_gap_doc()
    print(OUT_EXPL)
    print(OUT_GAP)
