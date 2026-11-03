from __future__ import annotations

import html
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from build_clean_assertion_master_real import any_true, max_int, normalize_assertion, parse_bool, parse_int


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"

SCALE120_ROOT = ROOT / "rtl_cases_real_scale120"
SCALE120_MANIFEST = SCALE120_ROOT / "case_manifest.json"
SCALE120_GOLDEN_FORMAL = ROOT / "outputs" / "golden_recheck_scale120_formal.csv"
SCALE120_HARDNESS_FORMAL = ROOT / "outputs" / "hardness_scale120_formal.csv"
CLEAN_MASTER = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
STRICT_REPORT = ROOT / "rtl_cases_real_admitted_20260619" / "strict_eval_report_iv12.csv"
MULTI_MODEL_RAW = ROOT / "outputs" / THREAD_ID / "multi_model_eval_data" / "multi_model_results_raw.csv"
OUTPUT_DIR = ROOT / "generated_main_results_strict_success"

MAIN_TABLE_XLSX = OUTPUT_DIR / "main_method_results.xlsx"
MAIN_QUADRANTS_XLSX = OUTPUT_DIR / "main_quadrant_results.xlsx"
CROSS_MODEL_XLSX = OUTPUT_DIR / "cross_model_strict_success.xlsx"
BENCHMARK_SUMMARY_XLSX = OUTPUT_DIR / "scale120_formal_benchmark_summary.xlsx"
OVERLAP_CASES_XLSX = OUTPUT_DIR / "scale120_eval_overlap_cases.xlsx"
SUMMARY_JSON = OUTPUT_DIR / "main_results_summary.json"
NOTES_MD = OUTPUT_DIR / "README.md"
FIGURE_JPG = OUTPUT_DIR / "main_results_figure.jpg"
WORKBOOK_XLSX = OUTPUT_DIR / "main_results_strict_success.xlsx"

QUADRANT_ORDER = [
    "Strict Success",
    "Missed Detection",
    "False Positive",
    "Both Errors",
]

BENCHMARK_METHOD_ORDER = [
    "spec_only",
    "spec_plus_rtl",
    "spec_rtl_raw_trace",
    "spec_rtl_trace_summary",
]
BENCHMARK_METHOD_LABEL = {
    "spec_only": "Spec only",
    "spec_plus_rtl": "Spec + RTL",
    "spec_rtl_raw_trace": "Spec + RTL + Raw Trace",
    "spec_rtl_trace_summary": "Spec + RTL + Trace Summary",
}

CROSS_MODEL_METHOD_ORDER = [
    "spec_only",
    "spec_plus_rtl",
    "spec_rtl_raw_trace",
    "spec_rtl_trace_summary",
    "spec_rtl_abstracted_trace_summary",
]
CROSS_MODEL_METHOD_LABEL = {
    "spec_only": "Spec only",
    "spec_plus_rtl": "Spec + RTL",
    "spec_rtl_raw_trace": "Spec + RTL + Raw Trace",
    "spec_rtl_trace_summary": "Spec + RTL + Trace Summary",
    "spec_rtl_abstracted_trace_summary": "Spec + RTL + Abstracted Summary",
}

MODEL_ORDER = ["GPT", "Claude", "Qwen"]
MODEL_COLORS = {
    "GPT": "#1b6ca8",
    "Claude": "#f28e2b",
    "Qwen": "#59a14f",
}
METHOD_MARKERS = {
    "Spec only": "o",
    "Spec + RTL": "o",
    "Spec + RTL + Raw Trace": "s",
    "Spec + RTL + Trace Summary": "^",
    "Spec + RTL + Abstracted Summary": "D",
}
METHOD_SHORT = {
    "Spec only": "Spec",
    "Spec + RTL": "RTL",
    "Spec + RTL + Raw Trace": "Raw",
    "Spec + RTL + Trace Summary": "Summary",
    "Spec + RTL + Abstracted Summary": "Abs",
}
BUG_CLASS_ORDER = ["combination_same_cycle", "temporal_cross_cycle", "overall"]


def safe_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    lowered = series.fillna(False).astype(str).str.strip().str.lower()
    return lowered.isin(["true", "1", "yes"])


def load_scale120_formal_baseline_df() -> pd.DataFrame:
    manifest_payload = json.loads(SCALE120_MANIFEST.read_text(encoding="utf-8"))
    manifest_rows: list[dict[str, object]] = []
    for case in manifest_payload["cases"]:
        seed_case_name = str(case.get("seed_case_name", "") or "").strip()
        manifest_rows.append(
            {
                "case_id": str(case["name"]),
                "scale120_bug_class": str(case.get("bug_class", "")),
                "scale120_bug_type": str(case.get("bug_type", "")),
                "scale120_source_project": str(case.get("source_project", "")),
                "scale120_source_module": str(case.get("source_module", "")),
                "scale120_seed_case_name": seed_case_name,
                "scale120_is_seed_slot": seed_case_name == "",
            }
        )
    manifest_df = pd.DataFrame(manifest_rows)

    golden_df = pd.read_csv(SCALE120_GOLDEN_FORMAL).rename(
        columns={
            "case_name": "case_id",
            "golden_ok": "scale120_golden_ok_formal",
            "reachability_gate_source": "scale120_reachability_gate_source",
            "antecedent_reachability_label": "scale120_antecedent_reachability",
            "effective_proof_status": "scale120_effective_proof_status",
        }
    )
    hardness_df = pd.read_csv(SCALE120_HARDNESS_FORMAL).rename(
        columns={
            "case_name": "case_id",
            "hardness_ok": "scale120_hardness_ok",
            "golden_reachability_source": "scale120_hardness_reachability_source",
            "golden_antecedent_reachability": "scale120_hardness_antecedent_reachability",
            "golden_effective_proof_status": "scale120_hardness_effective_proof_status",
        }
    )

    out = manifest_df.merge(
        golden_df[
            [
                "case_id",
                "scale120_golden_ok_formal",
                "scale120_reachability_gate_source",
                "scale120_antecedent_reachability",
                "scale120_effective_proof_status",
            ]
        ],
        on="case_id",
        how="left",
        validate="one_to_one",
    ).merge(
        hardness_df[
            [
                "case_id",
                "scale120_hardness_ok",
                "scale120_hardness_reachability_source",
                "scale120_hardness_antecedent_reachability",
                "scale120_hardness_effective_proof_status",
            ]
        ],
        on="case_id",
        how="left",
        validate="one_to_one",
    )

    for col in ["scale120_golden_ok_formal", "scale120_hardness_ok", "scale120_is_seed_slot"]:
        out[col] = safe_bool_series(out[col])
    return out


def attach_scale120_baseline(
    df: pd.DataFrame,
    scale120_baseline_df: pd.DataFrame,
    *,
    subset_name: str,
) -> pd.DataFrame:
    merged = df.merge(scale120_baseline_df, on="case_id", how="left", validate="many_to_one")
    missing = sorted(
        {
            str(case_id)
            for case_id in merged.loc[merged["scale120_bug_class"].isna(), "case_id"].dropna().astype(str)
        }
    )
    if missing:
        preview = ", ".join(missing[:8])
        extra = "" if len(missing) <= 8 else f" ... (+{len(missing) - 8} more)"
        raise ValueError(
            f"{subset_name} references case(s) that are not present in rtl_cases_real_scale120: {preview}{extra}"
        )

    merged["bug_class"] = merged["scale120_bug_class"]
    return merged


def load_clean_benchmark_df(scale120_baseline_df: pd.DataFrame) -> pd.DataFrame:
    clean_df = pd.read_csv(CLEAN_MASTER)
    raw_df = pd.read_csv(STRICT_REPORT)

    bool_cols = [
        "heldout_non_vacuous",
        "heldout_pass_on_correct",
        "heldout_fail_on_buggy",
    ]
    int_cols = [
        "candidate_index",
        "heldout_buggy_antecedent_hits",
        "heldout_correct_antecedent_hits",
    ]
    for col in bool_cols:
        raw_df[col] = raw_df[col].apply(parse_bool)
    for col in int_cols:
        raw_df[col] = raw_df[col].apply(parse_int)

    raw_df["case_id"] = raw_df["case_name"]
    raw_df["assertion_text"] = raw_df["assertion_line"].fillna("").astype(str).str.strip()
    raw_df = raw_df.loc[raw_df["assertion_text"] != ""].copy()
    raw_df["normalized_assertion"] = raw_df["assertion_text"].apply(normalize_assertion)
    raw_df = raw_df.sort_values(["case_id", "method", "normalized_assertion", "candidate_index"])

    rows: list[dict[str, object]] = []
    for (case_id, method, normalized_assertion), group in raw_df.groupby(
        ["case_id", "method", "normalized_assertion"],
        dropna=False,
        sort=False,
    ):
        heldout_correct_hits_max = max_int(group["heldout_correct_antecedent_hits"])
        heldout_buggy_hits_max = max_int(group["heldout_buggy_antecedent_hits"])
        rows.append(
            {
                "case_id": case_id,
                "method": method,
                "normalized_assertion": normalized_assertion,
                "heldout_correct_pass_exact": any_true(group["heldout_pass_on_correct"]),
                "heldout_buggy_fail_exact": any_true(group["heldout_fail_on_buggy"]),
                "heldout_antecedent_hit_exact": heldout_buggy_hits_max > 0,
                "heldout_non_vacuous_exact": any_true(group["heldout_non_vacuous"]),
                "heldout_correct_antecedent_hits_max_exact": heldout_correct_hits_max,
                "heldout_buggy_antecedent_hits_max_exact": heldout_buggy_hits_max,
            }
        )
    exact_df = pd.DataFrame(rows)
    merged = clean_df.merge(
        exact_df,
        on=["case_id", "method", "normalized_assertion"],
        how="left",
    )
    for col, exact_col in [
        ("heldout_correct_pass", "heldout_correct_pass_exact"),
        ("heldout_buggy_fail", "heldout_buggy_fail_exact"),
        ("heldout_antecedent_hit", "heldout_antecedent_hit_exact"),
        ("heldout_non_vacuous", "heldout_non_vacuous_exact"),
    ]:
        if exact_col in merged.columns:
            merged[col] = merged[exact_col].where(merged[exact_col].notna(), merged.get(col))
    return attach_scale120_baseline(
        merged,
        scale120_baseline_df,
        subset_name="main strict-success evaluated subset",
    )


def add_strict_metrics(
    df: pd.DataFrame,
    *,
    method_label_map: dict[str, str],
    non_vacuous_fallback_note: str,
) -> tuple[pd.DataFrame, str]:
    out = df.copy()
    for col in ["heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit"]:
        out[col] = safe_bool_series(out[col])

    if "heldout_non_vacuous" in out.columns:
        out["heldout_non_vacuous"] = safe_bool_series(out["heldout_non_vacuous"])
        non_vacuous_source = "heldout_non_vacuous column"
    else:
        out["heldout_non_vacuous"] = out["heldout_antecedent_hit"]
        non_vacuous_source = non_vacuous_fallback_note

    out["heldout_detect_bug"] = (
        out["heldout_buggy_fail"] & out["heldout_antecedent_hit"] & out["heldout_non_vacuous"]
    )
    out["strict_success_main"] = out["heldout_correct_pass"] & out["heldout_detect_bug"]
    out["mdr_event"] = ~out["heldout_detect_bug"]
    out["fpr_event"] = ~out["heldout_correct_pass"]

    out["quadrant"] = np.select(
        [
            out["heldout_correct_pass"] & out["heldout_detect_bug"],
            out["heldout_correct_pass"] & ~out["heldout_detect_bug"],
            ~out["heldout_correct_pass"] & out["heldout_detect_bug"],
        ],
        QUADRANT_ORDER[:3],
        default=QUADRANT_ORDER[3],
    )
    out["method_label"] = out["method"].map(method_label_map).fillna(out["method"])
    return out, non_vacuous_source


def summarize_candidate_group(sub: pd.DataFrame) -> dict[str, object]:
    total = int(len(sub))
    strict_success_count = int(sub["strict_success_main"].sum())
    detect_bug_count = int(sub["heldout_detect_bug"].sum())
    correct_pass_count = int(sub["heldout_correct_pass"].sum())
    fpr_count = total - correct_pass_count
    mdr_count = total - detect_bug_count

    row: dict[str, object] = {
        "candidate_count": total,
        "case_count": int(sub["case_id"].nunique()) if "case_id" in sub.columns else 0,
        "strict_success_count": strict_success_count,
        "strict_success_rate": strict_success_count / total if total else 0.0,
        "detect_bug_count": detect_bug_count,
        "detect_bug_rate": detect_bug_count / total if total else 0.0,
        "MDR_count": mdr_count,
        "MDR": mdr_count / total if total else 0.0,
        "FPR_count": fpr_count,
        "FPR": fpr_count / total if total else 0.0,
    }
    for quadrant in QUADRANT_ORDER:
        count = int((sub["quadrant"] == quadrant).sum())
        row[f"{quadrant}_count"] = count
        row[f"{quadrant}_share"] = count / total if total else 0.0
    return row


def aggregate_summary(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, sub in df.groupby(group_cols, dropna=False, sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {col: val for col, val in zip(group_cols, keys)}
        row.update(summarize_candidate_group(sub))
        rows.append(row)
    return pd.DataFrame(rows)


def build_main_tables(clean_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_parts = []
    quadrant_parts = []
    for bug_class in BUG_CLASS_ORDER:
        part = clean_df if bug_class == "overall" else clean_df.loc[clean_df["bug_class"] == bug_class].copy()
        summary = aggregate_summary(part, ["method", "method_label"])
        summary["bug_class"] = bug_class
        summary_parts.append(summary)

        for (method, method_label), sub in part.groupby(["method", "method_label"], dropna=False, sort=False):
            total = int(len(sub))
            for quadrant in QUADRANT_ORDER:
                count = int((sub["quadrant"] == quadrant).sum())
                quadrant_parts.append(
                    {
                        "method": method,
                        "method_label": method_label,
                        "bug_class": bug_class,
                        "quadrant": quadrant,
                        "candidate_count": count,
                        "share": count / total if total else 0.0,
                    }
                )

    main_df = pd.concat(summary_parts, ignore_index=True)
    main_df["method"] = pd.Categorical(main_df["method"], BENCHMARK_METHOD_ORDER, ordered=True)
    main_df["bug_class"] = pd.Categorical(main_df["bug_class"], BUG_CLASS_ORDER, ordered=True)
    main_df = main_df.sort_values(["bug_class", "method"]).reset_index(drop=True)
    main_df["method"] = main_df["method"].astype(str)
    main_df["bug_class"] = main_df["bug_class"].astype(str)

    quadrant_df = pd.DataFrame(quadrant_parts)
    quadrant_df["method"] = pd.Categorical(quadrant_df["method"], BENCHMARK_METHOD_ORDER, ordered=True)
    quadrant_df["bug_class"] = pd.Categorical(quadrant_df["bug_class"], BUG_CLASS_ORDER, ordered=True)
    quadrant_df["quadrant"] = pd.Categorical(quadrant_df["quadrant"], QUADRANT_ORDER, ordered=True)
    quadrant_df = quadrant_df.sort_values(["bug_class", "method", "quadrant"]).reset_index(drop=True)
    quadrant_df["method"] = quadrant_df["method"].astype(str)
    quadrant_df["bug_class"] = quadrant_df["bug_class"].astype(str)
    quadrant_df["quadrant"] = quadrant_df["quadrant"].astype(str)
    return main_df, quadrant_df


def build_cross_model_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    cross_df = aggregate_summary(raw_df, ["model_label", "provider", "model_name", "method", "method_label"])
    cross_df["model_label"] = pd.Categorical(cross_df["model_label"], MODEL_ORDER, ordered=True)
    cross_df["method"] = pd.Categorical(cross_df["method"], CROSS_MODEL_METHOD_ORDER, ordered=True)
    cross_df = cross_df.sort_values(["model_label", "method"]).reset_index(drop=True)
    cross_df["model_label"] = cross_df["model_label"].astype(str)
    cross_df["method"] = cross_df["method"].astype(str)
    return cross_df


def write_single_sheet_xlsx(df: pd.DataFrame, out_path: Path, sheet_name: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path) as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)


def svg_color_to_rgb(color: str) -> tuple[int, int, int]:
    text = str(color or "").strip()
    if text.startswith("#") and len(text) == 7:
        return tuple(int(text[i : i + 2], 16) for i in (1, 3, 5))
    if text.startswith("rgb(") and text.endswith(")"):
        parts = [part.strip() for part in text[4:-1].split(",")]
        if len(parts) == 3:
            return tuple(max(0, min(255, int(float(part)))) for part in parts)
    named = {
        "none": (255, 255, 255),
        "white": (255, 255, 255),
        "black": (0, 0, 0),
    }
    return named.get(text.lower(), (17, 24, 39))


def find_font_path() -> str | None:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def render_main_figure(main_df: pd.DataFrame, quadrant_df: pd.DataFrame, cross_df: pd.DataFrame) -> None:
    overall_main = main_df.loc[main_df["bug_class"] == "overall"].copy()
    overall_main["method"] = pd.Categorical(overall_main["method"], BENCHMARK_METHOD_ORDER, ordered=True)
    overall_main = overall_main.sort_values("method").reset_index(drop=True)

    overall_quadrant = quadrant_df.loc[quadrant_df["bug_class"] == "overall"].copy()
    overall_quadrant["method"] = pd.Categorical(overall_quadrant["method"], BENCHMARK_METHOD_ORDER, ordered=True)
    overall_quadrant["quadrant"] = pd.Categorical(overall_quadrant["quadrant"], QUADRANT_ORDER, ordered=True)
    overall_quadrant = overall_quadrant.sort_values(["method", "quadrant"]).reset_index(drop=True)

    cross_plot = cross_df.copy()
    cross_plot["model_label"] = pd.Categorical(cross_plot["model_label"], MODEL_ORDER, ordered=True)
    cross_plot["method"] = pd.Categorical(cross_plot["method"], CROSS_MODEL_METHOD_ORDER, ordered=True)
    cross_plot = cross_plot.sort_values(["method", "model_label"]).reset_index(drop=True)

    quadrant_colors = {
        "Strict Success": "#2a9d8f",
        "Missed Detection": "#e9c46a",
        "False Positive": "#f4a261",
        "Both Errors": "#b0b7c3",
    }
    heatmap = (
        cross_plot.pivot(index="method_label", columns="model_label", values="strict_success_rate")
        .reindex(
            index=[CROSS_MODEL_METHOD_LABEL[m] for m in CROSS_MODEL_METHOD_ORDER],
            columns=MODEL_ORDER,
        )
        .fillna(0.0)
    )

    width = 1600
    height = 1020
    panel_w = 700
    panel_h = 360
    left = 70
    top = 90
    gap_x = 90
    gap_y = 90
    raster = Image.new("RGB", (width, height), (255, 255, 255))
    raster_draw = ImageDraw.Draw(raster)
    font_path = find_font_path()
    font_cache: dict[tuple[int, str], ImageFont.ImageFont | ImageFont.FreeTypeFont] = {}

    def get_font(size: int, weight: str = "normal"):
        key = (size, weight)
        if key in font_cache:
            return font_cache[key]
        if font_path:
            try:
                font = ImageFont.truetype(font_path, size=size)
                font_cache[key] = font
                return font
            except OSError:
                pass
        font = ImageFont.load_default()
        font_cache[key] = font
        return font

    def esc(text: object) -> str:
        return html.escape(str(text))

    def rect(x, y, w, h, fill, stroke="#d1d5db", stroke_width=1, rx=0):
        fill_rgb = svg_color_to_rgb(fill)
        stroke_rgb = svg_color_to_rgb(stroke)
        xy = [x, y, x + w, y + h]
        if stroke == "none":
            stroke_rgb = None
        if rx:
            raster_draw.rounded_rectangle(xy, radius=rx, fill=fill_rgb, outline=stroke_rgb, width=int(stroke_width))
        else:
            raster_draw.rectangle(xy, fill=fill_rgb, outline=stroke_rgb, width=int(stroke_width))
        return (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" rx="{rx}" />'
        )

    def line(x1, y1, x2, y2, stroke="#374151", stroke_width=1):
        raster_draw.line((x1, y1, x2, y2), fill=svg_color_to_rgb(stroke), width=int(stroke_width))
        return (
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" />'
        )

    def text(x, y, content, size=13, anchor="start", weight="normal", fill="#111827"):
        use_font = get_font(size, weight)
        content_str = str(content)
        bbox = raster_draw.textbbox((0, 0), content_str, font=use_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw_x = x
        if anchor == "middle":
            draw_x = x - text_w / 2
        elif anchor == "end":
            draw_x = x - text_w
        draw_y = y - text_h * 0.82
        raster_draw.text((draw_x, draw_y), content_str, font=use_font, fill=svg_color_to_rgb(fill))
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-family="Arial, sans-serif" '
            f'text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">{esc(content)}</text>'
        )

    def circle(cx, cy, r, fill, stroke="white", stroke_width=1):
        raster_draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=svg_color_to_rgb(fill),
            outline=svg_color_to_rgb(stroke),
            width=int(stroke_width),
        )
        return (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" />'
        )

    def marker_symbol(cx, cy, kind, size, fill):
        half = size / 2
        if kind == "s":
            return rect(cx - half, cy - half, size, size, fill, stroke="white", stroke_width=1)
        if kind == "^":
            raster_draw.polygon(
                [(cx, cy - half), (cx - half, cy + half), (cx + half, cy + half)],
                fill=svg_color_to_rgb(fill),
                outline=svg_color_to_rgb("white"),
            )
            pts = f"{cx:.1f},{cy-half:.1f} {cx-half:.1f},{cy+half:.1f} {cx+half:.1f},{cy+half:.1f}"
            return f'<polygon points="{pts}" fill="{fill}" stroke="white" stroke-width="1" />'
        if kind == "D":
            raster_draw.polygon(
                [(cx, cy - half), (cx - half, cy), (cx, cy + half), (cx + half, cy)],
                fill=svg_color_to_rgb(fill),
                outline=svg_color_to_rgb("white"),
            )
            pts = f"{cx:.1f},{cy-half:.1f} {cx-half:.1f},{cy:.1f} {cx:.1f},{cy+half:.1f} {cx+half:.1f},{cy:.1f}"
            return f'<polygon points="{pts}" fill="{fill}" stroke="white" stroke-width="1" />'
        return circle(cx, cy, half, fill)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        rect(0, 0, width, height, "#ffffff", stroke="none"),
        text(
            width / 2,
            42,
            "Scale120 Formal-Aware Strict Success (Evaluated Overlap Subsets)",
            size=24,
            anchor="middle",
            weight="bold",
        ),
    ]

    panel_specs = {
        "A": (left, top, panel_w, panel_h, "Scale120 overlap subset: Strict Success, MDR, FPR"),
        "B": (left + panel_w + gap_x, top, panel_w, panel_h, "Scale120 overlap subset: Held-out Four Quadrants"),
        "C": (left, top + panel_h + gap_y, panel_w, panel_h, "Scale120 cross-model overlap subset"),
        "D": (left + panel_w + gap_x, top + panel_h + gap_y, panel_w, panel_h, "Scale120 cross-model MDR/FPR Tradeoff"),
    }
    for panel_id, (px, py, pw, ph, title) in panel_specs.items():
        parts.append(rect(px, py, pw, ph, "#fbfdff", stroke="#d7dee8", rx=12))
        parts.append(text(px + 18, py + 28, f"{panel_id}. {title}", size=17, weight="bold"))

    def draw_rate_axis(px, py, pw, ph):
        chart_left = px + 58
        chart_top = py + 62
        chart_w = pw - 90
        chart_h = ph - 112
        for tick in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = chart_top + chart_h * (1 - tick)
            parts.append(line(chart_left, y, chart_left + chart_w, y, stroke="#e5e7eb"))
            parts.append(text(chart_left - 10, y + 5, f"{tick:.2f}", size=11, anchor="end", fill="#6b7280"))
        parts.append(line(chart_left, chart_top, chart_left, chart_top + chart_h, stroke="#374151"))
        parts.append(line(chart_left, chart_top + chart_h, chart_left + chart_w, chart_top + chart_h, stroke="#374151"))
        return chart_left, chart_top, chart_w, chart_h

    # Panel A
    px, py, pw, ph, _ = panel_specs["A"]
    chart_left, chart_top, chart_w, chart_h = draw_rate_axis(px, py, pw, ph)
    metric_specs = [
        ("strict_success_rate", "Strict Success", "#2a9d8f"),
        ("MDR", "MDR", "#e76f51"),
        ("FPR", "FPR", "#577590"),
    ]
    group_w = chart_w / max(len(overall_main), 1)
    bar_w = min(38, group_w / 4.0)
    for i, (_, row) in enumerate(overall_main.iterrows()):
        center = chart_left + group_w * (i + 0.5)
        for j, (col, _, color) in enumerate(metric_specs):
            value = float(row[col])
            x = center + (j - 1) * (bar_w + 4) - bar_w / 2
            bar_h = chart_h * value
            y = chart_top + chart_h - bar_h
            parts.append(rect(x, y, bar_w, bar_h, color, stroke="none", rx=4))
            parts.append(text(x + bar_w / 2, y - 6, f"{value:.2f}", size=11, anchor="middle"))
        parts.append(text(center, chart_top + chart_h + 22, row["method_label"], size=11, anchor="middle"))
    legend_x = chart_left + 6
    legend_y = py + ph - 18
    for idx, (_, label, color) in enumerate(metric_specs):
        lx = legend_x + idx * 170
        parts.append(rect(lx, legend_y - 11, 18, 12, color, stroke="none", rx=2))
        parts.append(text(lx + 26, legend_y, label, size=12))

    # Panel B
    px, py, pw, ph, _ = panel_specs["B"]
    chart_left, chart_top, chart_w, chart_h = draw_rate_axis(px, py, pw, ph)
    bar_w = min(70, chart_w / (len(BENCHMARK_METHOD_ORDER) * 1.6))
    for i, method in enumerate(BENCHMARK_METHOD_ORDER):
        center = chart_left + chart_w * (i + 0.5) / len(BENCHMARK_METHOD_ORDER)
        bottom = chart_top + chart_h
        for quadrant in QUADRANT_ORDER[::-1]:
            match = overall_quadrant.loc[
                (overall_quadrant["method"] == method) & (overall_quadrant["quadrant"] == quadrant),
                "share",
            ]
            share = float(match.iloc[0]) if not match.empty else 0.0
            seg_h = chart_h * share
            y = bottom - seg_h
            parts.append(rect(center - bar_w / 2, y, bar_w, seg_h, quadrant_colors[quadrant], stroke="white", stroke_width=1))
            if share >= 0.08:
                parts.append(text(center, y + seg_h / 2 + 4, f"{share:.2f}", size=11, anchor="middle"))
            bottom = y
        parts.append(text(center, chart_top + chart_h + 22, BENCHMARK_METHOD_LABEL[method], size=11, anchor="middle"))
    legend_x = chart_left
    legend_y = py + ph - 18
    for idx, quadrant in enumerate(QUADRANT_ORDER):
        lx = legend_x + (idx % 2) * 250
        ly = legend_y - (idx // 2) * 18
        parts.append(rect(lx, ly - 11, 18, 12, quadrant_colors[quadrant], stroke="none", rx=2))
        parts.append(text(lx + 26, ly, quadrant, size=12))

    # Panel C
    px, py, pw, ph, _ = panel_specs["C"]
    cell_w = 155
    cell_h = 54
    start_x = px + 185
    start_y = py + 90
    for j, model in enumerate(MODEL_ORDER):
        parts.append(text(start_x + j * cell_w + cell_w / 2, start_y - 16, model, size=13, anchor="middle", weight="bold"))
    for i, method_label in enumerate(heatmap.index.tolist()):
        parts.append(text(start_x - 14, start_y + i * cell_h + cell_h / 2 + 5, method_label, size=12, anchor="end"))
        for j, model in enumerate(heatmap.columns.tolist()):
            value = float(heatmap.iloc[i, j])
            green = int(245 - value * 90)
            fill = f"rgb({220 - int(value * 60)},{green},{195 - int(value * 40)})"
            x = start_x + j * cell_w
            y = start_y + i * cell_h
            parts.append(rect(x, y, cell_w - 6, cell_h - 6, fill, stroke="#d1d5db", rx=6))
            parts.append(text(x + (cell_w - 6) / 2, y + 31, f"{value:.2f}", size=16, anchor="middle", weight="bold"))

    # Panel D
    px, py, pw, ph, _ = panel_specs["D"]
    chart_left = px + 66
    chart_top = py + 62
    chart_w = pw - 118
    chart_h = ph - 120
    for tick in [0.0, 0.25, 0.5, 0.75, 1.0]:
        x = chart_left + chart_w * tick
        y = chart_top + chart_h * (1 - tick)
        parts.append(line(x, chart_top, x, chart_top + chart_h, stroke="#eef2f7"))
        parts.append(line(chart_left, y, chart_left + chart_w, y, stroke="#eef2f7"))
        parts.append(text(x, chart_top + chart_h + 22, f"{tick:.2f}", size=11, anchor="middle", fill="#6b7280"))
        parts.append(text(chart_left - 10, y + 5, f"{tick:.2f}", size=11, anchor="end", fill="#6b7280"))
    parts.append(line(chart_left, chart_top, chart_left, chart_top + chart_h, stroke="#374151"))
    parts.append(line(chart_left, chart_top + chart_h, chart_left + chart_w, chart_top + chart_h, stroke="#374151"))
    parts.append(text(chart_left + chart_w / 2, chart_top + chart_h + 48, "FPR", size=13, anchor="middle", weight="bold"))
    parts.append(text(chart_left - 46, chart_top + chart_h / 2, "MDR", size=13, anchor="middle", weight="bold"))
    for _, row in cross_plot.iterrows():
        model = str(row["model_label"])
        method_label = str(row["method_label"])
        cx = chart_left + chart_w * float(row["FPR"])
        cy = chart_top + chart_h * float(row["MDR"])
        parts.append(marker_symbol(cx, cy, METHOD_MARKERS.get(method_label, "o"), 14, MODEL_COLORS.get(model, "#333333")))
        parts.append(text(cx + 10, cy - 8, f"{model}/{METHOD_SHORT.get(method_label, method_label)}", size=10))
    legend_x = px + pw - 215
    legend_y = py + 96
    for idx, model in enumerate(MODEL_ORDER):
        ly = legend_y + idx * 18
        parts.append(circle(legend_x, ly - 4, 6, MODEL_COLORS[model]))
        parts.append(text(legend_x + 14, ly, model, size=11))
    method_legend_y = legend_y + 66
    for idx, method_label in enumerate([CROSS_MODEL_METHOD_LABEL[m] for m in CROSS_MODEL_METHOD_ORDER]):
        ly = method_legend_y + idx * 18
        parts.append(marker_symbol(legend_x, ly - 4, METHOD_MARKERS[method_label], 12, "#6b7280"))
        parts.append(text(legend_x + 14, ly, METHOD_SHORT[method_label], size=11))

    parts.append("</svg>")
    raster.save(FIGURE_JPG, format="JPEG", quality=95)


def write_workbook(
    main_df: pd.DataFrame,
    quadrant_df: pd.DataFrame,
    cross_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    overlap_df: pd.DataFrame,
    notes_rows: list[dict[str, str]],
) -> str:
    try:
        with pd.ExcelWriter(WORKBOOK_XLSX) as writer:
            benchmark_df.to_excel(writer, sheet_name="scale120_benchmark", index=False)
            overlap_df.to_excel(writer, sheet_name="scale120_overlaps", index=False)
            main_df.to_excel(writer, sheet_name="main_method_results", index=False)
            quadrant_df.to_excel(writer, sheet_name="main_quadrants", index=False)
            cross_df.to_excel(writer, sheet_name="cross_model", index=False)
            pd.DataFrame(notes_rows).to_excel(writer, sheet_name="README", index=False)
        return "ok"
    except Exception as exc:  # pragma: no cover - best-effort export
        return f"failed: {exc}"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    scale120_baseline = load_scale120_formal_baseline_df()
    full_multi_model_raw_env = os.environ.get("STRICT_SUCCESS_FULL_MULTI_MODEL_RAW", "").strip()
    primary_model_label = os.environ.get("STRICT_SUCCESS_PRIMARY_MODEL_LABEL", "GPT").strip() or "GPT"

    clean_source_desc = (
        f"{CLEAN_MASTER.relative_to(ROOT)} + exact held-out fields from "
        f"{STRICT_REPORT.relative_to(ROOT)}, then joined to scale120 formal-aware benchmark metadata"
    )
    cross_model_source_desc = (
        f"{MULTI_MODEL_RAW.relative_to(ROOT)}, then joined to scale120 formal-aware benchmark metadata"
    )

    if full_multi_model_raw_env:
        full_multi_model_raw_path = Path(full_multi_model_raw_env).resolve()
        full_multi_model_raw = attach_scale120_baseline(
            pd.read_csv(full_multi_model_raw_path),
            scale120_baseline,
            subset_name="full multi-model evaluated subset",
        )
        multi_model_raw = full_multi_model_raw
        cross_model_source_desc = (
            f"{full_multi_model_raw_path.relative_to(ROOT)}, then joined to scale120 formal-aware benchmark metadata"
        )

        primary_model_df = full_multi_model_raw.loc[
            (full_multi_model_raw["model_label"].astype(str) == primary_model_label)
            & (full_multi_model_raw["method"].astype(str).isin(BENCHMARK_METHOD_ORDER))
        ].copy()
        if not primary_model_df.empty:
            clean_raw = primary_model_df
            clean_source_desc = (
                f"{full_multi_model_raw_path.relative_to(ROOT)} filtered to model_label={primary_model_label}, "
                "then joined to scale120 formal-aware benchmark metadata"
            )
        else:
            clean_raw = load_clean_benchmark_df(scale120_baseline)
    else:
        clean_raw = load_clean_benchmark_df(scale120_baseline)
        multi_model_raw = attach_scale120_baseline(
            pd.read_csv(MULTI_MODEL_RAW),
            scale120_baseline,
            subset_name="cross-model evaluated subset",
        )

    clean_df, clean_non_vacuous_source = add_strict_metrics(
        clean_raw,
        method_label_map=BENCHMARK_METHOD_LABEL,
        non_vacuous_fallback_note="fallback to heldout_antecedent_hit because clean master lacks heldout_non_vacuous",
    )
    multi_model_df, multi_model_non_vacuous_source = add_strict_metrics(
        multi_model_raw,
        method_label_map=CROSS_MODEL_METHOD_LABEL,
        non_vacuous_fallback_note="fallback to heldout_antecedent_hit because raw table lacks heldout_non_vacuous",
    )

    main_df, quadrant_df = build_main_tables(clean_df)
    cross_df = build_cross_model_table(multi_model_df)

    write_single_sheet_xlsx(main_df, MAIN_TABLE_XLSX, "main_method_results")
    write_single_sheet_xlsx(quadrant_df, MAIN_QUADRANTS_XLSX, "main_quadrants")
    write_single_sheet_xlsx(cross_df, CROSS_MODEL_XLSX, "cross_model")

    benchmark_summary_df = pd.DataFrame(
        [
            {
                "benchmark_root": str(SCALE120_ROOT.relative_to(ROOT)),
                "total_case_count": int(len(scale120_baseline)),
                "seed_slot_count": int(scale120_baseline["scale120_is_seed_slot"].sum()),
                "augmentation_case_count": int((~scale120_baseline["scale120_is_seed_slot"]).sum()),
                "formal_golden_pass_count": int(scale120_baseline["scale120_golden_ok_formal"].sum()),
                "formal_hardness_pass_count": int(scale120_baseline["scale120_hardness_ok"].sum()),
                "formal_golden_source": str(SCALE120_GOLDEN_FORMAL.relative_to(ROOT)),
                "formal_hardness_source": str(SCALE120_HARDNESS_FORMAL.relative_to(ROOT)),
            }
        ]
    )
    write_single_sheet_xlsx(benchmark_summary_df, BENCHMARK_SUMMARY_XLSX, "scale120_benchmark")

    overlap_case_df = scale120_baseline[
        [
            "case_id",
            "scale120_bug_class",
            "scale120_bug_type",
            "scale120_source_project",
            "scale120_source_module",
            "scale120_is_seed_slot",
            "scale120_seed_case_name",
            "scale120_golden_ok_formal",
            "scale120_hardness_ok",
            "scale120_antecedent_reachability",
            "scale120_effective_proof_status",
        ]
    ].copy()
    main_case_ids = set(clean_df["case_id"].astype(str).unique())
    cross_case_ids = set(multi_model_df["case_id"].astype(str).unique())
    overlap_case_df["in_main_eval_subset"] = overlap_case_df["case_id"].astype(str).isin(main_case_ids)
    overlap_case_df["in_cross_model_subset"] = overlap_case_df["case_id"].astype(str).isin(cross_case_ids)
    write_single_sheet_xlsx(overlap_case_df, OVERLAP_CASES_XLSX, "scale120_overlaps")

    render_main_figure(main_df, quadrant_df, cross_df)

    notes_rows = [
        {
            "field": "strict_success_definition",
            "value": "heldout_correct_pass == 1 AND heldout_buggy_fail == 1 AND heldout_antecedent_hit == 1 AND heldout_non_vacuous == 1",
        },
        {
            "field": "detect_bug_definition",
            "value": "heldout_buggy_fail == 1 AND heldout_antecedent_hit == 1 AND heldout_non_vacuous == 1",
        },
        {
            "field": "MDR_definition",
            "value": "1 - detect_bug_rate",
        },
        {
            "field": "FPR_definition",
            "value": "1 - heldout_correct_pass_rate",
        },
        {
            "field": "benchmark_root",
            "value": str(SCALE120_ROOT.relative_to(ROOT)),
        },
        {
            "field": "formal_benchmark_source",
            "value": (
                f"{SCALE120_GOLDEN_FORMAL.relative_to(ROOT)} + "
                f"{SCALE120_HARDNESS_FORMAL.relative_to(ROOT)}"
            ),
        },
        {
            "field": "main_evaluated_subset_source",
            "value": clean_source_desc,
        },
        {
            "field": "cross_model_source",
            "value": cross_model_source_desc,
        },
        {
            "field": "clean_main_non_vacuous_source",
            "value": clean_non_vacuous_source,
        },
        {
            "field": "cross_model_non_vacuous_source",
            "value": multi_model_non_vacuous_source,
        },
        {
            "field": "main_overlap_case_count",
            "value": str(int(clean_df["case_id"].nunique())),
        },
        {
            "field": "cross_model_overlap_case_count",
            "value": str(int(multi_model_df["case_id"].nunique())),
        },
    ]
    workbook_status = write_workbook(
        main_df,
        quadrant_df,
        cross_df,
        benchmark_summary_df,
        overlap_case_df,
        notes_rows,
    )

    overall_main = main_df.loc[main_df["bug_class"] == "overall"].copy()
    best_main = overall_main.sort_values(
        ["strict_success_rate", "MDR", "FPR"],
        ascending=[False, True, True],
    ).iloc[0]
    best_cross = cross_df.sort_values(
        ["strict_success_rate", "MDR", "FPR"],
        ascending=[False, True, True],
    ).iloc[0]

    summary_payload = {
        "strict_success_definition": "heldout_correct_pass && heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous",
        "benchmark_root": str(SCALE120_ROOT.relative_to(ROOT)),
        "benchmark_total_case_count": int(len(scale120_baseline)),
        "benchmark_seed_slot_count": int(scale120_baseline["scale120_is_seed_slot"].sum()),
        "benchmark_augmentation_case_count": int((~scale120_baseline["scale120_is_seed_slot"]).sum()),
        "benchmark_formal_golden_pass_count": int(scale120_baseline["scale120_golden_ok_formal"].sum()),
        "benchmark_formal_hardness_pass_count": int(scale120_baseline["scale120_hardness_ok"].sum()),
        "main_evaluated_subset_source": clean_source_desc,
        "main_candidate_count": int(len(clean_df)),
        "main_case_count": int(clean_df["case_id"].nunique()),
        "main_eval_overlap_case_count": int(clean_df["case_id"].nunique()),
        "cross_model_source": cross_model_source_desc,
        "cross_model_candidate_count": int(len(multi_model_df)),
        "cross_model_case_count": int(multi_model_df["case_id"].nunique()),
        "cross_model_overlap_case_count": int(multi_model_df["case_id"].nunique()),
        "best_main_method": {
            "method": str(best_main["method"]),
            "method_label": str(best_main["method_label"]),
            "strict_success_rate": float(best_main["strict_success_rate"]),
            "MDR": float(best_main["MDR"]),
            "FPR": float(best_main["FPR"]),
        },
        "best_cross_model_cell": {
            "model_label": str(best_cross["model_label"]),
            "method": str(best_cross["method"]),
            "method_label": str(best_cross["method_label"]),
            "strict_success_rate": float(best_cross["strict_success_rate"]),
            "MDR": float(best_cross["MDR"]),
            "FPR": float(best_cross["FPR"]),
        },
        "overlap_case_inventory_xlsx": str(OVERLAP_CASES_XLSX.relative_to(ROOT)),
        "scale120_formal_benchmark_summary_xlsx": str(BENCHMARK_SUMMARY_XLSX.relative_to(ROOT)),
        "workbook_status": workbook_status,
    }
    SUMMARY_JSON.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    notes_text = "\n".join(
        [
            "# Main Results (Strict Success)",
            "",
            "- Primary metric: `strict_success = heldout_correct_pass & heldout_buggy_fail & heldout_antecedent_hit & heldout_non_vacuous`",
            "- Detection rate: `1 - MDR` where `detect_bug = heldout_buggy_fail & heldout_antecedent_hit & heldout_non_vacuous`",
            "- False positive rate: `FPR = 1 - heldout_correct_pass_rate`",
            "- Four quadrants are defined on `(heldout_correct_pass, detect_bug)`.",
            "",
            "## Outputs",
            "",
            f"- `{BENCHMARK_SUMMARY_XLSX.relative_to(ROOT)}`",
            f"- `{OVERLAP_CASES_XLSX.relative_to(ROOT)}`",
            f"- `{MAIN_TABLE_XLSX.relative_to(ROOT)}`",
            f"- `{MAIN_QUADRANTS_XLSX.relative_to(ROOT)}`",
            f"- `{CROSS_MODEL_XLSX.relative_to(ROOT)}`",
            f"- `{FIGURE_JPG.relative_to(ROOT)}`",
            f"- `{WORKBOOK_XLSX.relative_to(ROOT)}`",
            "",
            "## Notes",
            "",
            f"- Canonical benchmark root: `{SCALE120_ROOT.relative_to(ROOT)}`",
            (
                f"- Formal-aware benchmark gate sources: `{SCALE120_GOLDEN_FORMAL.relative_to(ROOT)}` "
                f"and `{SCALE120_HARDNESS_FORMAL.relative_to(ROOT)}`"
            ),
            (
                f"- Full scale120 benchmark coverage: {int(len(scale120_baseline))} cases "
                f"= {int(scale120_baseline['scale120_is_seed_slot'].sum())} seed slots + "
                f"{int((~scale120_baseline['scale120_is_seed_slot']).sum())} augmentation cases"
            ),
            (
                f"- Main method table is the evaluated overlap subset inside scale120: "
                f"{int(clean_df['case_id'].nunique())} cases / {int(len(scale120_baseline))} total scale120 cases"
            ),
            (
                f"- Cross-model table is the evaluated overlap subset inside scale120: "
                f"{int(multi_model_df['case_id'].nunique())} cases / {int(len(scale120_baseline))} total scale120 cases"
            ),
            f"- Clean benchmark non-vacuous source: {clean_non_vacuous_source}",
            f"- Cross-model non-vacuous source: {multi_model_non_vacuous_source}",
            f"- Workbook export status: {workbook_status}",
        ]
    )
    NOTES_MD.write_text(notes_text, encoding="utf-8")

    print(MAIN_TABLE_XLSX)
    print(MAIN_QUADRANTS_XLSX)
    print(CROSS_MODEL_XLSX)
    print(BENCHMARK_SUMMARY_XLSX)
    print(OVERLAP_CASES_XLSX)
    print(FIGURE_JPG)
    print(WORKBOOK_XLSX)


if __name__ == "__main__":
    main()
