from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from run_trace_abstraction_prototype import (  # noqa: E402
    CASES_ROOT,
    MODEL_NAME,
    OLLAMA_URL,
    extract_sva_candidates,
    extract_rtl_from_prompt,
    extract_waveform_guidance,
    judge_semantic_reasonable,
    parse_allowed_signals,
    post_ollama,
    probe_property_support,
    read_text,
    run_case_eval,
    write_text,
)


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "trace_selection_data"
WINDOW_SIZE = 4


@dataclass
class CaseMeta:
    case_id: str
    selection_reason: str
    bug_class: str
    temporal_kind: str
    literal_lure_signals: list[str]


SELECTED_CASES: list[CaseMeta] = [
    CaseMeta(
        case_id="case101_prim_onehot_multihot_suppressed",
        selection_reason="Same-cycle multihot case with obvious literal overfit risk on oh_i patterns.",
        bug_class="combination_same_cycle",
        temporal_kind="same_cycle",
        literal_lure_signals=["oh_i[3:0]", "addr_i[1:0]"],
    ),
    CaseMeta(
        case_id="case104_prim_fifo_full_early",
        selection_reason="Boundary case where a good trace should include the last pre-full step instead of only the failing literal.",
        bug_class="combination_same_cycle",
        temporal_kind="same_cycle",
        literal_lure_signals=["depth_o[2:0]", "wptr_o[1:0]"],
    ),
    CaseMeta(
        case_id="case112_prim_intr_test_pulse_dropped",
        selection_reason="Temporal pulse-capture case where a weak snippet often misses the qe trigger entirely.",
        bug_class="temporal_cross_cycle",
        temporal_kind="temporal",
        literal_lure_signals=["reg2hw_intr_test_q_i"],
    ),
    CaseMeta(
        case_id="case124_prim_fifo_clear_ignored",
        selection_reason="Temporal clear case where a good snippet must include both pre-clear occupancy and the clear response.",
        bug_class="temporal_cross_cycle",
        temporal_kind="temporal",
        literal_lure_signals=["depth_o[2:0]"],
    ),
    CaseMeta(
        case_id="case125_prim_fifo_wrap_late",
        selection_reason="Wrap-boundary case with strong hardcoding temptation on depth and pointer literals.",
        bug_class="temporal_cross_cycle",
        temporal_kind="temporal",
        literal_lure_signals=["depth_o[2:0]", "wptr_o[1:0]"],
    ),
    CaseMeta(
        case_id="case126_prim_regwe_enable_gap",
        selection_reason="Same-cycle enable mismatch case where bad snippets encourage memorizing one observed onehot bit.",
        bug_class="combination_same_cycle",
        temporal_kind="same_cycle",
        literal_lure_signals=["oh_i[3:0]"],
    ),
    CaseMeta(
        case_id="case130_prim_fifo_empty_early",
        selection_reason="Boundary case where one-entry context matters; low-quality snippets often show only post-failure empty states.",
        bug_class="combination_same_cycle",
        temporal_kind="same_cycle",
        literal_lure_signals=["depth_o[2:0]"],
    ),
    CaseMeta(
        case_id="case135_prim_intr_enable_mask_ignored",
        selection_reason="Masked interrupt case where the useful snippet must include state-high plus enable-low, not only the earlier event.",
        bug_class="combination_same_cycle",
        temporal_kind="same_cycle",
        literal_lure_signals=[],
    ),
]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def parse_cycle_trace(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"cycle\s+(\d+):\s*(.*)$", line, flags=re.IGNORECASE)
        if not match:
            continue
        cycle = int(match.group(1))
        payload = match.group(2)
        signals: dict[str, str] = {}
        for item in payload.split(","):
            item = item.strip()
            if not item or "=" not in item:
                continue
            key, value = item.split("=", 1)
            signals[key.strip()] = value.strip()
        rows.append({"cycle": cycle, "signals": signals})
    return rows


def bits_to_int(value: str) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return 0
    if re.fullmatch(r"[01]+", text):
        return int(text, 2)
    if re.fullmatch(r"\d+", text):
        return int(text, 10)
    return 0


def bit_popcount(value: str) -> int:
    text = str(value or "").strip()
    if re.fullmatch(r"[01]+", text):
        return text.count("1")
    number = bits_to_int(text)
    return bin(number).count("1")


def signal_value(cycle_row: dict[str, Any], signal_name: str) -> str:
    return str(cycle_row["signals"].get(signal_name, ""))


def is_true(value: str) -> bool:
    return bits_to_int(value) != 0


def diff_signals(good_row: dict[str, Any], bad_row: dict[str, Any]) -> list[str]:
    signals = sorted(set(good_row["signals"]) | set(bad_row["signals"]))
    out = []
    for sig in signals:
        if sig == "clk":
            continue
        if signal_value(good_row, sig) != signal_value(bad_row, sig):
            out.append(sig)
    return out


def is_nontrivial_literal(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    if re.fullmatch(r"[01]{2,}", text):
        return bits_to_int(text) > 1
    if re.fullmatch(r"\d+", text):
        return int(text, 10) > 1
    return False


def trace_value_sets(good_trace: list[dict[str, Any]], bad_trace: list[dict[str, Any]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in [*good_trace, *bad_trace]:
        for sig, value in row["signals"].items():
            out.setdefault(sig, set()).add(str(value))
    return out


def trigger_case101(g: dict[str, Any], _b: dict[str, Any], _idx: int, *_all: Any) -> bool:
    return is_true(signal_value(g, "rst_n")) and is_true(signal_value(g, "en_i")) and bit_popcount(signal_value(g, "oh_i[3:0]")) >= 2


def trigger_case104(g: dict[str, Any], _b: dict[str, Any], _idx: int, *_all: Any) -> bool:
    return (
        is_true(signal_value(g, "rst_n"))
        and is_true(signal_value(g, "incr_wptr_i"))
        and not is_true(signal_value(g, "incr_rptr_i"))
        and bits_to_int(signal_value(g, "depth_o[2:0]")) == 3
        and not is_true(signal_value(g, "full_o"))
    )


def trigger_case112(g: dict[str, Any], _b: dict[str, Any], _idx: int, *_all: Any) -> bool:
    return is_true(signal_value(g, "rst_n")) and is_true(signal_value(g, "reg2hw_intr_test_qe_i"))


def trigger_case124(g: dict[str, Any], _b: dict[str, Any], idx: int, all_good: list[dict[str, Any]], *_all: Any) -> bool:
    prev_depth = bits_to_int(signal_value(all_good[idx - 1], "depth_o[2:0]")) if idx > 0 else 0
    return is_true(signal_value(g, "rst_n")) and is_true(signal_value(g, "clr_i")) and prev_depth > 0


def trigger_case125(g: dict[str, Any], _b: dict[str, Any], idx: int, all_good: list[dict[str, Any]], *_all: Any) -> bool:
    prev_depth = bits_to_int(signal_value(all_good[idx - 1], "depth_o[2:0]")) if idx > 0 else 0
    return (
        is_true(signal_value(g, "rst_n"))
        and is_true(signal_value(g, "incr_wptr_i"))
        and prev_depth == 3
        and bits_to_int(signal_value(g, "depth_o[2:0]")) == 4
    )


def trigger_case126(g: dict[str, Any], _b: dict[str, Any], _idx: int, *_all: Any) -> bool:
    return is_true(signal_value(g, "rst_n")) and not is_true(signal_value(g, "en_i")) and bits_to_int(signal_value(g, "oh_i[3:0]")) != 0


def trigger_case130(g: dict[str, Any], b: dict[str, Any], _idx: int, *_all: Any) -> bool:
    return (
        is_true(signal_value(g, "rst_n"))
        and bits_to_int(signal_value(g, "depth_o[2:0]")) == 1
        and not is_true(signal_value(g, "empty_o"))
        and is_true(signal_value(b, "empty_o"))
    )


def trigger_case135(g: dict[str, Any], _b: dict[str, Any], _idx: int, *_all: Any) -> bool:
    return (
        is_true(signal_value(g, "rst_n"))
        and not is_true(signal_value(g, "reg2hw_intr_enable_q_i"))
        and is_true(signal_value(g, "reg2hw_intr_state_q_i"))
    )


TRIGGER_FUNCS: dict[str, Callable[..., bool]] = {
    "case101_prim_onehot_multihot_suppressed": trigger_case101,
    "case104_prim_fifo_full_early": trigger_case104,
    "case112_prim_intr_test_pulse_dropped": trigger_case112,
    "case124_prim_fifo_clear_ignored": trigger_case124,
    "case125_prim_fifo_wrap_late": trigger_case125,
    "case126_prim_regwe_enable_gap": trigger_case126,
    "case130_prim_fifo_empty_early": trigger_case130,
    "case135_prim_intr_enable_mask_ignored": trigger_case135,
}


def case_meta_map() -> dict[str, CaseMeta]:
    return {item.case_id: item for item in SELECTED_CASES}


def first_divergence_index(good_trace: list[dict[str, Any]], bad_trace: list[dict[str, Any]]) -> int | None:
    for idx in range(min(len(good_trace), len(bad_trace))):
        if diff_signals(good_trace[idx], bad_trace[idx]):
            return idx
    return None


def heldout_trigger_relation(case_id: str, good_trace: list[dict[str, Any]], bad_trace: list[dict[str, Any]]) -> tuple[bool, bool]:
    trigger_fn = TRIGGER_FUNCS[case_id]
    for idx in range(min(len(good_trace), len(bad_trace))):
        if not trigger_fn(good_trace[idx], bad_trace[idx], idx, good_trace, bad_trace):
            continue
        if diff_signals(good_trace[idx], bad_trace[idx]):
            return True, True
        if idx + 1 < min(len(good_trace), len(bad_trace)) and diff_signals(good_trace[idx + 1], bad_trace[idx + 1]):
            return True, True
        return True, False
    return False, False


def make_generation_prompt(
    *,
    allowed_signals: list[str],
    spec: str,
    rtl_text: str,
    trace_section: str,
    additional_guidance: str,
) -> str:
    guidance_block = f"\nAdditional guidance:\n{additional_guidance}\n" if additional_guidance else ""
    return textwrap.dedent(
        f"""
        You are a formal verification engineer.
        Generate exactly five distinct SystemVerilog Assertions in this strict format, one assertion per line:
        assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));

        Rules:
        1) Output exactly five assertion lines total. No explanation. No markdown. No numbering.
        2) Use only allowed signals listed below.
        3) Keep antecedent and consequent purely boolean (no ##, no $past, no sequence operators).
        4) No helper/internal names such as next_state, count_next, count_prev, old(...), S_*.
        5) Each candidate must contain exactly one implication operator total: either one |-> or one |=>.
        6) Prefer candidates that pass on good behavior and fail on bad behavior.
        7) Avoid vacuous antecedents: choose conditions that actually appear in the observed traces.
        8) Infer a reusable relation, not a one-off witnessed cycle.
        9) Do not hard-code observed literals such as initial addresses, specific state encodings, or one-off values unless the spec or RTL independently justifies them.
        10) Make the five candidates meaningfully different in antecedent/consequent structure, while staying semantically faithful.

        Allowed signals:
        {", ".join(allowed_signals)}

        Specification:
        {spec}
        {guidance_block}
        RTL:
        {rtl_text}

        {trace_section}
        """
    ).strip()


def collect_candidates(prompt: str, *, target_count: int) -> tuple[list[str], list[str]]:
    collected: list[str] = []
    raw_responses: list[str] = []
    temperatures = [0.6, 0.8, 1.0]
    for temp in temperatures:
        attempt_prompt = prompt
        if collected:
            attempt_prompt += (
                "\n\nDo not repeat any previous candidate. Already seen:\n- "
                + "\n- ".join(collected)
            )
        response = post_ollama(attempt_prompt, temperature=temp)
        raw_responses.append(response)
        for cand in extract_sva_candidates(response):
            if cand not in collected:
                collected.append(cand)
            if len(collected) >= target_count:
                return collected[:target_count], raw_responses
    return collected[:target_count], raw_responses


def format_window_trace(window_good: list[dict[str, Any]], window_bad: list[dict[str, Any]]) -> str:
    def fmt(prefix: str, rows: list[dict[str, Any]]) -> str:
        lines = [prefix]
        for row in rows:
            payload = ", ".join(f"{k}={v}" for k, v in row["signals"].items())
            lines.append(f"cycle {row['cycle']}: {payload}")
        return "\n".join(lines)

    return fmt("Good trace snippet (posedge cycles):", window_good) + "\n\n" + fmt("Bad trace snippet (posedge cycles):", window_bad)


def score_window(
    *,
    case_meta: CaseMeta,
    seen_good: list[dict[str, Any]],
    seen_bad: list[dict[str, Any]],
    heldout_good: list[dict[str, Any]],
    heldout_bad: list[dict[str, Any]],
    start: int,
    window_size: int,
    heldout_value_sets: dict[str, set[str]],
    heldout_trigger_seen: bool,
    heldout_relation_seen: bool,
) -> dict[str, Any]:
    trigger_fn = TRIGGER_FUNCS[case_meta.case_id]
    good_w = seen_good[start : start + window_size]
    bad_w = seen_bad[start : start + window_size]
    local_diffs = [diff_signals(g, b) for g, b in zip(good_w, bad_w)]
    first_div_local = next((idx for idx, item in enumerate(local_diffs) if item), None)

    if first_div_local is None:
        divergence_clear = 0
    else:
        divergence_clear = 1 + int(first_div_local > 0)

    trigger_hits_local = [
        idx
        for idx in range(len(good_w))
        if trigger_fn(good_w[idx], bad_w[idx], start + idx, seen_good, seen_bad)
    ]
    if not trigger_hits_local:
        antecedent_cover = 0
    else:
        aligned = False
        for t in trigger_hits_local:
            if first_div_local is None:
                continue
            if first_div_local == t or first_div_local == t + 1:
                aligned = True
                break
        antecedent_cover = 2 if aligned else 1

    if case_meta.temporal_kind == "temporal":
        if any(t < len(good_w) - 1 for t in trigger_hits_local):
            temporal_depth = 2
        elif trigger_hits_local:
            temporal_depth = 1
        else:
            temporal_depth = 0
    else:
        temporal_depth = 1 if trigger_hits_local else 0

    if not trigger_hits_local:
        heldout_consistency = 0
    elif heldout_relation_seen:
        heldout_consistency = 2
    elif heldout_trigger_seen:
        heldout_consistency = 1
    else:
        heldout_consistency = 0

    focus_indices = set(trigger_hits_local)
    if first_div_local is not None:
        focus_indices.add(first_div_local)
    unseen_lure_hits: set[tuple[str, str]] = set()
    any_lure_literal = False
    for idx in sorted(focus_indices):
        for sig in case_meta.literal_lure_signals:
            for row in (good_w[idx], bad_w[idx]):
                value = signal_value(row, sig)
                if not is_nontrivial_literal(value):
                    continue
                any_lure_literal = True
                if value not in heldout_value_sets.get(sig, set()):
                    unseen_lure_hits.add((sig, value))
    if unseen_lure_hits:
        literal_risk = 2
    elif any_lure_literal:
        literal_risk = 1
    else:
        literal_risk = 0

    total_score = divergence_clear + antecedent_cover + temporal_depth + heldout_consistency - literal_risk
    first_div_cycle = good_w[first_div_local]["cycle"] if first_div_local is not None else None
    diff_summary = ", ".join(local_diffs[first_div_local]) if first_div_local is not None else ""

    notes: list[str] = []
    if divergence_clear == 0:
        notes.append("no clear good/bad divergence inside snippet")
    elif first_div_local == 0:
        notes.append("snippet starts after divergence has already happened")
    else:
        notes.append("snippet contains matching prelude before first divergence")
    if antecedent_cover == 0:
        notes.append("missing bug-trigger condition")
    elif antecedent_cover == 1:
        notes.append("trigger appears but effect alignment is weak")
    else:
        notes.append("trigger and bug effect are both visible")
    if literal_risk == 2:
        notes.append("strong unseen-literal hardcoding risk")
    elif literal_risk == 1:
        notes.append("contains concrete boundary literals")
    if heldout_consistency == 2:
        notes.append("held-out trace shows the same trigger/effect pattern")
    elif heldout_consistency == 1:
        notes.append("held-out trace contains the trigger but with weaker alignment evidence")

    return {
        "case_id": case_meta.case_id,
        "bug_class": case_meta.bug_class,
        "temporal_kind": case_meta.temporal_kind,
        "window_start_index": start,
        "window_end_index": start + len(good_w) - 1,
        "window_start_cycle": good_w[0]["cycle"],
        "window_end_cycle": good_w[-1]["cycle"],
        "window_size": len(good_w),
        "divergence_clear": divergence_clear,
        "antecedent_cover": antecedent_cover,
        "literal_risk": literal_risk,
        "temporal_depth": temporal_depth,
        "heldout_consistency": heldout_consistency,
        "total_score": total_score,
        "trigger_hit_count": len(trigger_hits_local),
        "first_divergence_local_index": first_div_local if first_div_local is not None else "",
        "first_divergence_cycle": first_div_cycle if first_div_cycle is not None else "",
        "first_divergence_signals": diff_summary,
        "selected_trace_text": format_window_trace(good_w, bad_w),
        "selection_notes": "; ".join(notes),
    }


def rank_windows(window_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    high = sorted(
        window_rows,
        key=lambda row: (
            -int(row["total_score"]),
            -int(row["antecedent_cover"]),
            -int(row["divergence_clear"]),
            -int(row["heldout_consistency"]),
            int(row["literal_risk"]),
            int(row["window_start_cycle"]),
        ),
    )[0]
    low = sorted(
        window_rows,
        key=lambda row: (
            int(row["total_score"]),
            int(row["antecedent_cover"]),
            int(row["divergence_clear"]),
            int(row["heldout_consistency"]),
            -int(row["literal_risk"]),
            int(row["window_start_cycle"]),
        ),
    )[0]
    if high["window_start_cycle"] == low["window_start_cycle"] and len(window_rows) > 1:
        low = sorted(
            [row for row in window_rows if row["window_start_cycle"] != high["window_start_cycle"]],
            key=lambda row: (
                int(row["total_score"]),
                int(row["antecedent_cover"]),
                int(row["divergence_clear"]),
                int(row["heldout_consistency"]),
                -int(row["literal_risk"]),
                int(row["window_start_cycle"]),
            ),
        )[0]
    return high, low


def case_prompt_bundle(case_meta: CaseMeta) -> dict[str, Any]:
    case_dir = CASES_ROOT / case_meta.case_id / "experiment"
    raw_prompt_src = read_text(case_dir / "prompts" / "prompt_3_spec_rtl_raw_trace.txt")
    allowed_signals = parse_allowed_signals(raw_prompt_src)
    rtl_text = extract_rtl_from_prompt(raw_prompt_src)
    additional_guidance = extract_waveform_guidance(raw_prompt_src)
    spec = read_text(case_dir / "spec.txt").strip()
    seen_good = parse_cycle_trace(read_text(case_dir / "trace_good.txt"))
    seen_bad = parse_cycle_trace(read_text(case_dir / "trace_bad.txt"))
    heldout_good = parse_cycle_trace(read_text(case_dir / "trace_good_holdout.txt"))
    heldout_bad = parse_cycle_trace(read_text(case_dir / "trace_bad_holdout.txt"))
    return {
        "case_meta": case_meta,
        "allowed_signals": allowed_signals,
        "rtl_text": rtl_text,
        "additional_guidance": additional_guidance,
        "spec": spec,
        "seen_good": seen_good,
        "seen_bad": seen_bad,
        "heldout_good": heldout_good,
        "heldout_bad": heldout_bad,
    }


def persist_progress(all_results: list[dict[str, Any]], window_rows: list[dict[str, Any]], selected_rows: list[dict[str, Any]]) -> None:
    if window_rows:
        pd.DataFrame(window_rows).to_csv(
            OUTPUT_DIR / "trace_quality_scored_windows.csv",
            index=False,
            encoding="utf-8-sig",
        )
    if selected_rows:
        pd.DataFrame(selected_rows).to_csv(
            OUTPUT_DIR / "trace_quality_selected_windows.csv",
            index=False,
            encoding="utf-8-sig",
        )
    if all_results:
        pd.DataFrame(all_results).to_csv(
            OUTPUT_DIR / "high_vs_low_quality_trace_results_raw.csv",
            index=False,
            encoding="utf-8-sig",
        )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    case_filter = {
        item.strip()
        for item in os.environ.get("TRACESEL_CASE_FILTER", "").split(",")
        if item.strip()
    }
    quality_filter = {
        item.strip()
        for item in os.environ.get("TRACESEL_QUALITY_FILTER", "").split(",")
        if item.strip()
    }
    max_cases = int(os.environ.get("TRACESEL_MAX_CASES", "0") or "0")
    candidates_per_variant = int(os.environ.get("TRACESEL_CANDIDATES_PER_VARIANT", "5") or "5")

    selected_cases = [item for item in SELECTED_CASES if not case_filter or item.case_id in case_filter]
    if max_cases > 0:
        selected_cases = selected_cases[:max_cases]
    if not selected_cases:
        raise RuntimeError("No cases selected after TRACESEL_CASE_FILTER / TRACESEL_MAX_CASES.")

    bundles = [case_prompt_bundle(item) for item in selected_cases]
    use_property = probe_property_support(bundles[0]["case_meta"].case_id)

    all_window_rows: list[dict[str, Any]] = []
    selected_window_rows: list[dict[str, Any]] = []
    all_results: list[dict[str, Any]] = []
    results_csv = OUTPUT_DIR / "high_vs_low_quality_trace_results_raw.csv"
    if results_csv.exists():
        existing_df = pd.read_csv(results_csv)
        if not existing_df.empty:
            all_results = existing_df.to_dict(orient="records")

    for bundle in bundles:
        meta: CaseMeta = bundle["case_meta"]
        case_id = meta.case_id
        prompt_dir = OUTPUT_DIR / "prompts" / case_id
        prompt_dir.mkdir(parents=True, exist_ok=True)

        heldout_value_sets = trace_value_sets(bundle["heldout_good"], bundle["heldout_bad"])
        heldout_trigger_seen, heldout_relation_seen = heldout_trigger_relation(
            case_id,
            bundle["heldout_good"],
            bundle["heldout_bad"],
        )
        pair_len = min(len(bundle["seen_good"]), len(bundle["seen_bad"]))
        if pair_len < WINDOW_SIZE:
            raise RuntimeError(f"{case_id}: trace length {pair_len} is shorter than window size {WINDOW_SIZE}.")

        case_window_rows: list[dict[str, Any]] = []
        for start in range(0, pair_len - WINDOW_SIZE + 1):
            row = score_window(
                case_meta=meta,
                seen_good=bundle["seen_good"],
                seen_bad=bundle["seen_bad"],
                heldout_good=bundle["heldout_good"],
                heldout_bad=bundle["heldout_bad"],
                start=start,
                window_size=WINDOW_SIZE,
                heldout_value_sets=heldout_value_sets,
                heldout_trigger_seen=heldout_trigger_seen,
                heldout_relation_seen=heldout_relation_seen,
            )
            case_window_rows.append(row)
            all_window_rows.append(row)

        high_row, low_row = rank_windows(case_window_rows)
        for quality_name, row in [("high_quality_trace", high_row), ("low_quality_trace", low_row)]:
            selected_window_rows.append(
                {
                    **row,
                    "selected_trace_quality": quality_name,
                    "selection_reason": meta.selection_reason,
                    "prompt_path": str((prompt_dir / f"{quality_name}_prompt.txt").resolve()),
                }
            )

            if quality_filter and quality_name not in quality_filter:
                continue

            prompt_text = make_generation_prompt(
                allowed_signals=bundle["allowed_signals"],
                spec=bundle["spec"],
                rtl_text=bundle["rtl_text"],
                trace_section=row["selected_trace_text"],
                additional_guidance=bundle["additional_guidance"],
            )
            write_text(prompt_dir / f"{quality_name}_prompt.txt", prompt_text)

            existing_variant_rows = [
                item
                for item in all_results
                if item.get("case_id") == case_id and item.get("selected_trace_quality") == quality_name
            ]
            if len(existing_variant_rows) >= candidates_per_variant:
                continue
            if 0 < len(existing_variant_rows) < candidates_per_variant:
                all_results = [
                    item
                    for item in all_results
                    if not (item.get("case_id") == case_id and item.get("selected_trace_quality") == quality_name)
                ]

            candidates, raw_responses = collect_candidates(prompt_text, target_count=candidates_per_variant)
            candidates = candidates[:candidates_per_variant]
            if len(candidates) < candidates_per_variant:
                raise RuntimeError(f"{case_id}/{quality_name}: only collected {len(candidates)} candidates.")

            judge_map = judge_semantic_reasonable(
                spec=bundle["spec"],
                case_id=case_id,
                candidates=candidates,
            )
            for candidate_idx, assertion_text in enumerate(candidates, start=1):
                runtime_dir = OUTPUT_DIR / "runtime" / case_id / quality_name / f"cand_{candidate_idx:02d}"
                eval_result = run_case_eval(
                    case_id=case_id,
                    assertion_text=assertion_text,
                    signal_names=bundle["allowed_signals"],
                    use_property=use_property,
                    runtime_dir=runtime_dir,
                )
                judge_info = judge_map.get(
                    str(candidate_idx),
                    {"semantic_reasonable": False, "semantic_reason": "judge_missing"},
                )
                all_results.append(
                    {
                        "case_id": case_id,
                        "bug_class": meta.bug_class,
                        "temporal_kind": meta.temporal_kind,
                        "selected_trace_quality": quality_name,
                        "window_start_cycle": row["window_start_cycle"],
                        "window_end_cycle": row["window_end_cycle"],
                        "total_score": row["total_score"],
                        "divergence_clear": row["divergence_clear"],
                        "antecedent_cover": row["antecedent_cover"],
                        "literal_risk": row["literal_risk"],
                        "temporal_depth": row["temporal_depth"],
                        "heldout_consistency": row["heldout_consistency"],
                        "candidate_index": candidate_idx,
                        "assertion_text": assertion_text,
                        "compile_ok": eval_result["compile_ok"],
                        "correct_pass": eval_result["correct_pass"],
                        "buggy_fail": eval_result["buggy_fail"],
                        "antecedent_hit": eval_result["antecedent_hit"],
                        "non_vacuous": eval_result["non_vacuous"],
                        "heldout_correct_pass": eval_result["heldout_correct_pass"],
                        "heldout_buggy_fail": eval_result["heldout_buggy_fail"],
                        "heldout_antecedent_hit": eval_result["heldout_antecedent_hit"],
                        "trace_overfit": eval_result["trace_overfit"],
                        "semantic_reasonable": judge_info["semantic_reasonable"],
                        "semantic_reason": judge_info["semantic_reason"],
                        "seen_good_ant_hits": eval_result["seen_good_ant_hits"],
                        "seen_bad_ant_hits": eval_result["seen_bad_ant_hits"],
                        "heldout_bad_ant_hits": eval_result["heldout_bad_ant_hits"],
                        "seen_good_fail_hits": eval_result["seen_good_fail_hits"],
                        "seen_bad_fail_hits": eval_result["seen_bad_fail_hits"],
                        "heldout_good_fail_hits": eval_result["heldout_good_fail_hits"],
                        "heldout_bad_fail_hits": eval_result["heldout_bad_fail_hits"],
                        "use_property_compile_mode": use_property,
                        "selected_trace_text": row["selected_trace_text"],
                        "selection_notes": row["selection_notes"],
                        "raw_generation_responses": "\n\n===== NEXT RESPONSE =====\n\n".join(raw_responses),
                    }
                )
                persist_progress(all_results, all_window_rows, selected_window_rows)

    window_df = pd.DataFrame(all_window_rows).sort_values(["case_id", "window_start_cycle"]).reset_index(drop=True)
    selected_df = pd.DataFrame(selected_window_rows).sort_values(["case_id", "selected_trace_quality"]).reset_index(drop=True)
    results_df = pd.DataFrame(all_results).sort_values(["case_id", "selected_trace_quality", "candidate_index"]).reset_index(drop=True)

    window_df.to_csv(OUTPUT_DIR / "trace_quality_scored_windows.csv", index=False, encoding="utf-8-sig")
    selected_df.to_csv(OUTPUT_DIR / "trace_quality_selected_windows.csv", index=False, encoding="utf-8-sig")
    results_df.to_csv(OUTPUT_DIR / "high_vs_low_quality_trace_results_raw.csv", index=False, encoding="utf-8-sig")

    summary_rows = []
    if not results_df.empty:
        for (case_id, quality_name), sub in results_df.groupby(["case_id", "selected_trace_quality"], dropna=False):
            summary_rows.append(
                {
                    "case_id": case_id,
                    "selected_trace_quality": quality_name,
                    "candidate_count": int(len(sub)),
                    "compile_ok_count": int(sub["compile_ok"].sum()),
                    "correct_pass_count": int(sub["correct_pass"].sum()),
                    "buggy_fail_count": int(sub["buggy_fail"].sum()),
                    "antecedent_hit_count": int(sub["antecedent_hit"].sum()),
                    "non_vacuous_count": int(sub["non_vacuous"].sum()),
                    "heldout_correct_pass_count": int(sub["heldout_correct_pass"].sum()),
                    "heldout_buggy_fail_count": int(sub["heldout_buggy_fail"].sum()),
                    "trace_overfit_count": int(sub["trace_overfit"].sum()),
                    "semantic_reasonable_count": int(sub["semantic_reasonable"].sum()),
                    "avg_window_score": float(sub["total_score"].mean()),
                }
            )
    summary_df = pd.DataFrame(summary_rows).sort_values(["case_id", "selected_trace_quality"]).reset_index(drop=True)
    summary_df.to_csv(OUTPUT_DIR / "high_vs_low_quality_trace_summary.csv", index=False, encoding="utf-8-sig")

    comparison_rows = []
    if not results_df.empty:
        for case_id, sub in results_df.groupby("case_id", dropna=False):
            high = sub[sub["selected_trace_quality"] == "high_quality_trace"]
            low = sub[sub["selected_trace_quality"] == "low_quality_trace"]

            def rate(frame: pd.DataFrame, col: str) -> float:
                if frame.empty:
                    return 0.0
                return float(frame[col].mean())

            comparison_rows.append(
                {
                    "case_id": case_id,
                    "high_window_score": high["total_score"].iloc[0] if not high.empty else "",
                    "low_window_score": low["total_score"].iloc[0] if not low.empty else "",
                    "delta_window_score": (high["total_score"].iloc[0] - low["total_score"].iloc[0]) if (not high.empty and not low.empty) else "",
                    "high_correct_pass_rate": rate(high, "correct_pass"),
                    "low_correct_pass_rate": rate(low, "correct_pass"),
                    "delta_correct_pass_rate": rate(high, "correct_pass") - rate(low, "correct_pass"),
                    "high_buggy_fail_rate": rate(high, "buggy_fail"),
                    "low_buggy_fail_rate": rate(low, "buggy_fail"),
                    "delta_buggy_fail_rate": rate(high, "buggy_fail") - rate(low, "buggy_fail"),
                    "high_antecedent_hit_rate": rate(high, "antecedent_hit"),
                    "low_antecedent_hit_rate": rate(low, "antecedent_hit"),
                    "delta_antecedent_hit_rate": rate(high, "antecedent_hit") - rate(low, "antecedent_hit"),
                    "high_heldout_success_rate": rate(high, "heldout_correct_pass") * rate(high, "heldout_buggy_fail"),
                    "low_heldout_success_rate": rate(low, "heldout_correct_pass") * rate(low, "heldout_buggy_fail"),
                    "delta_heldout_success_rate": (rate(high, "heldout_correct_pass") * rate(high, "heldout_buggy_fail")) - (rate(low, "heldout_correct_pass") * rate(low, "heldout_buggy_fail")),
                    "high_trace_overfit_rate": rate(high, "trace_overfit"),
                    "low_trace_overfit_rate": rate(low, "trace_overfit"),
                    "delta_trace_overfit_rate": rate(high, "trace_overfit") - rate(low, "trace_overfit"),
                }
            )
    comparison_df = pd.DataFrame(comparison_rows).sort_values("case_id").reset_index(drop=True)
    comparison_df.to_csv(OUTPUT_DIR / "high_vs_low_quality_case_comparison.csv", index=False, encoding="utf-8-sig")

    write_text(
        OUTPUT_DIR / "selected_cases.json",
        json.dumps(
            [
                {
                    "case_id": item.case_id,
                    "selection_reason": item.selection_reason,
                    "bug_class": item.bug_class,
                    "temporal_kind": item.temporal_kind,
                    "literal_lure_signals": item.literal_lure_signals,
                }
                for item in selected_cases
            ],
            indent=2,
            ensure_ascii=False,
        ),
    )
    write_text(
        OUTPUT_DIR / "trace_selection_run_meta.json",
        json.dumps(
            {
                "model_name": MODEL_NAME,
                "ollama_url": OLLAMA_URL,
                "window_size": WINDOW_SIZE,
                "selected_case_count": len(selected_cases),
                "candidates_per_variant": candidates_per_variant,
                "prompt_variants": ["high_quality_trace", "low_quality_trace"],
                "use_property_compile_mode": use_property,
                "case_filter": sorted(case_filter),
                "quality_filter": sorted(quality_filter),
                "max_cases": max_cases,
                "argv": sys.argv,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )

    print(OUTPUT_DIR / "trace_quality_scored_windows.csv")
    print(OUTPUT_DIR / "high_vs_low_quality_trace_results_raw.csv")
    print(OUTPUT_DIR / "high_vs_low_quality_trace_summary.csv")


if __name__ == "__main__":
    main()
