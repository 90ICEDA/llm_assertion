from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

import pandas as pd

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from run_trace_abstraction_prototype import (
    CASES_ROOT,
    MODEL_NAME,
    OLLAMA_URL,
    extract_rtl_from_prompt,
    parse_allowed_signals,
    post_ollama,
    probe_property_support,
    read_text,
    run_case_eval,
    split_assertion,
    write_text,
)


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
SOURCE_CLEAN = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
SOURCE_REP = ROOT / "outputs" / THREAD_ID / "vacuity_analysis_data" / "representative_failures_vacuity_priority.csv"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "antecedent_repair_data"

PROMPT_FILE_MAP = {
    "prompt_1_spec_only": "prompt_1_spec_only.txt",
    "prompt_2_spec_plus_rtl": "prompt_2_spec_plus_rtl.txt",
    "prompt_3_spec_rtl_raw_trace": "prompt_3_spec_rtl_raw_trace.txt",
    "prompt_4_spec_rtl_trace_summary": "prompt_4_spec_rtl_trace_summary.txt",
}

SELECTED_CASES: list[dict[str, str]] = [
    {
        "case_id": "case101_prim_onehot_multihot_suppressed",
        "selection_reason": "原始 consequent=err_o 本身是对的，问题主要是 antecedent 过窄，要求四个 bit 同时为 1。",
        "trigger_condition_summary": (
            "The bug-revealing condition is an enabled multi-hot request: en_i is high and more than one bit of oh_i is high "
            "in the same sampled cycle. The observed primary trace injects 4'b1010 and 4'b0110, while held-out uses different "
            "multi-hot literals. The repaired antecedent should generalize the multi-hot relation instead of matching one specific literal."
        ),
        "antecedent_failure_diagnosis": "Original antecedent required all four bits of oh_i to be high at once, which never occurs in the buggy trace.",
    },
    {
        "case_id": "case102_prim_onehot_enable_mismatch_suppressed",
        "selection_reason": "原始 consequent=err_o 仍然可用，主要是 antecedent 只盯住 mismatch 的一个方向。",
        "trigger_condition_summary": (
            "The bug-revealing condition is an enable mismatch: en_i disagrees with whether any onehot bit is set. "
            "In the primary trace, the first miss is the zero-hot but enabled corner (oh_i is all zero while en_i is 1). "
            "Held-out also exercises the opposite mismatch direction with a nonzero onehot pattern while en_i is 0. "
            "The repaired antecedent should cover the disagreement relation, not only one observed direction."
        ),
        "antecedent_failure_diagnosis": "Original antecedent excluded the zero-hot while enabled mismatch that actually triggers the bug in the primary trace.",
    },
    {
        "case_id": "case103_prim_onehot_addr_mismatch_suppressed",
        "selection_reason": "原始 consequent=err_o 对应了真正错误信号，主要问题是 antecedent 自己写成了 reset 相关或过泛条件。",
        "trigger_condition_summary": (
            "The bug-revealing condition is a legal onehot request whose addr_i points to a different bit in the same cycle. "
            "Good trace sweeps matching and mismatching addr_i values while keeping oh_i onehot. Held-out uses different active bits. "
            "The repaired antecedent should encode onehot-and-wrong-index consistency, not reset-related or always-true request checks."
        ),
        "antecedent_failure_diagnosis": "Original antecedent included !rst_n under disable iff (!rst_n), making the trigger impossible after reset, or otherwise failed to encode the onehot/address mismatch relation.",
    },
    {
        "case_id": "case112_prim_intr_test_pulse_dropped",
        "selection_reason": "原始 consequent=hw2reg_intr_state_d_o 是对的；antecedent 只差一个错误的 reset conjunct。",
        "trigger_condition_summary": (
            "The bug-revealing condition is a one-cycle software test pulse through reg2hw_intr_test_qe_i while Status mode is active. "
            "On the next cycle, good raises hw2reg_intr_state_d_o but bad keeps it low. "
            "The repaired antecedent should target the test pulse itself, without reintroducing reset gating inside the antecedent."
        ),
        "antecedent_failure_diagnosis": "Original antecedent appended !rst_n inside an assertion that already disables during reset, so it never fired on the sampled test pulse.",
    },
    {
        "case_id": "case124_prim_fifo_clear_ignored",
        "selection_reason": "原始 consequent=depth_o==0 仍然是清晰有效的 next-cycle check，问题是 antecedent 又把 !rst_n 写进去了。",
        "trigger_condition_summary": (
            "The bug-revealing condition is an operational clear pulse clr_i while the FIFO is non-empty. "
            "On the next cycle, good resets occupancy/pointers and depth_o becomes zero, while bad retains stale occupancy. "
            "Held-out clears from a different occupancy level, so the antecedent should stay tied to clr_i rather than any one observed depth literal."
        ),
        "antecedent_failure_diagnosis": "Original antecedent required clr_i && !rst_n, which cannot trigger because reset cycles are excluded by disable iff.",
    },
    {
        "case_id": "case125_prim_fifo_wrap_late",
        "selection_reason": "原始 consequent=wptr_o==0 还有价值，主要是 antecedent 用了错误的 boundary relation。",
        "trigger_condition_summary": (
            "The bug-revealing condition is a write at the wrap boundary: the internal write pointer is at the last valid slot and incr_wptr_i is asserted. "
            "On the next cycle, good wraps wptr_o to 0, while bad delays the wrap by one cycle. "
            "Held-out includes a read before the final wrap sequence, so the antecedent should describe the boundary-write situation rather than a brittle arithmetic coincidence."
        ),
        "antecedent_failure_diagnosis": "Original antecedent used a mismatched arithmetic relation between wptr_o and depth_o, so it never matched the actual wrap-boundary write in the buggy trace.",
    },
    {
        "case_id": "case135_prim_intr_enable_mask_ignored",
        "selection_reason": "原始 consequent=intr_o==0 是对 masked corner 的正确检查，主要是 antecedent 锁在 event pulse 而不是 latched state。",
        "trigger_condition_summary": (
            "The bug-revealing condition is the masked-state corner: reg2hw_intr_state_q_i is already high while reg2hw_intr_enable_q_i is low. "
            "Good keeps intr_o low in that sampled cycle, while bad leaks intr_o high. "
            "The repaired antecedent should target the already-latched interrupt state under a low enable mask, not the earlier event pulse."
        ),
        "antecedent_failure_diagnosis": "Original antecedent watched event_intr_i when the bug actually appears later, after state is latched and enable drops low.",
    },
    {
        "case_id": "case137_prim_onehot_addr_false_positive",
        "selection_reason": "原始 consequent=!err_o 与 spec 一致，适合观察 antecedent 从错误合法条件修到真正 legal corner 之后的收益。",
        "trigger_condition_summary": (
            "The bug-revealing condition is a legal onehot request whose addr_i matches the active bit in the same cycle. "
            "Good keeps err_o low for that legal request, while bad spuriously raises err_o. "
            "Held-out uses a different legal bit/index match, so the antecedent should encode the legal onehot/index relation instead of a single observed literal or malformed concatenation."
        ),
        "antecedent_failure_diagnosis": "Original antecedent tried to describe the legal address relation with a malformed or overly specific expression that never matched the buggy trace.",
    },
]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def load_selected_rows() -> pd.DataFrame:
    rep = pd.read_csv(SOURCE_REP)
    clean = pd.read_csv(SOURCE_CLEAN)
    wanted = {item["case_id"] for item in SELECTED_CASES}
    rep = rep[rep["case_id"].isin(wanted)].copy()
    merged = rep.merge(
        clean[
            [
                "case_id",
                "module",
                "bug_name",
                "bug_class",
                "method",
                "prompt_type",
                "assertion_text",
                "normalized_assertion",
                "compile_ok",
                "analysis_supported",
                "template_supported",
                "correct_pass",
                "fail_on_buggy",
                "antecedent_hit_correct",
                "antecedent_hit_buggy",
                "non_vacuous_correct",
                "non_vacuous_buggy",
                "heldout_correct_pass",
                "heldout_buggy_fail",
                "heldout_antecedent_hit",
                "trace_overfit",
                "literal_hardcoding",
                "failure_type",
                "failure_reason",
            ]
        ],
        on=["case_id", "module", "bug_name", "bug_class", "method", "assertion_text"],
        how="left",
    )
    meta_df = pd.DataFrame(SELECTED_CASES)
    merged = merged.merge(meta_df, on="case_id", how="left")
    merged["selection_order"] = merged["case_id"].map({item["case_id"]: idx for idx, item in enumerate(SELECTED_CASES, start=1)})
    merged = merged.sort_values("selection_order").reset_index(drop=True)
    return merged


def method_context(case_id: str, prompt_type: str) -> tuple[list[str], str, str, str, str, str]:
    exp_dir = CASES_ROOT / case_id / "experiment"
    prompt_file = exp_dir / "prompts" / PROMPT_FILE_MAP[prompt_type]
    prompt_text = read_text(prompt_file)
    allowed_signals = parse_allowed_signals(prompt_text)
    spec = read_text(exp_dir / "spec.txt").strip()
    trace_good = read_text(exp_dir / "trace_good.txt").strip()
    trace_bad = read_text(exp_dir / "trace_bad.txt").strip()
    trace_summary = read_text(exp_dir / "trace_summary.txt").strip()
    rtl_text = ""
    if prompt_type != "prompt_1_spec_only":
        rtl_text = extract_rtl_from_prompt(prompt_text)
    return allowed_signals, spec, rtl_text, trace_good, trace_bad, trace_summary


def prompt_context_block(prompt_type: str, trace_good: str, trace_bad: str, trace_summary: str, rtl_text: str) -> str:
    blocks = []
    if rtl_text:
        blocks.append("RTL context:\n" + rtl_text)
    if prompt_type == "prompt_3_spec_rtl_raw_trace":
        blocks.append(f"Observed good trace (posedge cycles):\n{trace_good}\n\nObserved bad trace (posedge cycles):\n{trace_bad}")
    elif prompt_type == "prompt_4_spec_rtl_trace_summary":
        blocks.append("Observed trace summary:\n" + trace_summary)
    elif prompt_type == "prompt_2_spec_plus_rtl":
        blocks.append("Observed trace summary for repair guidance:\n" + trace_summary)
    else:
        blocks.append("Observed trace summary extracted for repair guidance:\n" + trace_summary)
    return "\n\n".join(blocks).strip()


def repair_prompt(row: pd.Series) -> str:
    allowed_signals, spec, rtl_text, trace_good, trace_bad, trace_summary = method_context(row["case_id"], row["prompt_type"])
    antecedent, implication, consequent = split_assertion(str(row["assertion_text"]))
    summary_path = CASES_ROOT / row["case_id"] / "experiment" / "trace_summary.json"
    trace_summary_json = json.loads(read_text(summary_path))
    divergence_items = trace_summary_json.get("divergence_snapshot", [])
    divergence_line = "; ".join(
        f"{item['signal']}: good={item['good']} bad={item['bad']}" for item in divergence_items
    ) or "n/a"

    context_block = prompt_context_block(row["prompt_type"], trace_good, trace_bad, trace_summary, rtl_text)
    return textwrap.dedent(
        f"""
        You are repairing only the antecedent of a SystemVerilog assertion.

        Output exactly five antecedent expressions, one per line.
        Do not output assertion syntax.
        Do not output explanations.
        Do not number the lines.

        Case: {row['case_id']}
        Original method: {row['method']}
        Allowed signals:
        {", ".join(allowed_signals)}

        Specification:
        {spec}

        Original assertion:
        {row['assertion_text']}

        Locked implication operator:
        {implication}

        Locked consequent:
        {consequent}

        Why the original antecedent failed to trigger:
        - Original antecedent: {antecedent}
        - Diagnosis: {row['antecedent_failure_diagnosis']}

        Trigger condition extracted from the good/bad traces:
        - {row['trigger_condition_summary']}
        - First divergence cycle: {trace_summary_json.get('first_divergence_cycle', 'n/a')}
        - First divergence values: {divergence_line}

        Repair rules:
        1) Repair only the antecedent. We will reuse the locked implication operator and locked consequent exactly as given.
        2) Use only allowed signals.
        3) Do not include !rst_n in the antecedent because the assertion already has disable iff (!rst_n).
        4) Prefer an antecedent that actually fires on the bug-revealing scenario in the observed buggy trace.
        5) Preserve correctness on the good trace if possible.
        6) Do not hardcode one observed literal unless the spec or RTL independently justifies it.
        7) If the consequent is checked on the next cycle ({implication}), make the antecedent describe the precondition of that next-cycle effect.

        {context_block}
        """
    ).strip()


def extract_antecedent_candidates(response: str) -> list[str]:
    lines = []
    for raw_line in response.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\d+[\).\s-]+", "", line).strip()
        line = line.strip("`")
        if line.lower().startswith("assert property"):
            try:
                ant, _, _ = split_assertion(line)
                line = ant
            except Exception:
                continue
        if any(token in line.lower() for token in ["locked consequent", "diagnosis:", "because", "rationale"]):
            continue
        if "|" in line and ("|->" in line or "|=>" in line):
            continue
        if line.endswith(";"):
            line = line[:-1].strip()
        if line:
            lines.append(line)
    deduped = []
    seen = set()
    for line in lines:
        norm = normalize_space(line)
        if norm not in seen:
            deduped.append(line)
            seen.add(norm)
    return deduped


def collect_repair_candidates(prompt_text: str, *, case_id: str) -> tuple[list[str], list[str]]:
    collected: list[str] = []
    raw_responses: list[str] = []
    for temperature in (0.2, 0.5, 0.8):
        attempt_prompt = prompt_text
        if collected:
            attempt_prompt += "\n\nDo not repeat these antecedents:\n- " + "\n- ".join(collected)
        response = post_ollama(attempt_prompt, temperature=temperature)
        raw_responses.append(response)
        for candidate in extract_antecedent_candidates(response):
            if candidate not in collected:
                collected.append(candidate)
            if len(collected) >= 5:
                return collected[:5], raw_responses
    return collected[:5], raw_responses


def build_assertion(antecedent: str, implication: str, consequent: str) -> str:
    return f"assert property (@(posedge clk) disable iff (!rst_n) ({antecedent}) {implication} ({consequent}));"


def candidate_score(result: dict[str, Any]) -> tuple:
    return (
        int(bool(result["compile_ok"])),
        int(bool(result["correct_pass"])),
        int(bool(result["buggy_fail"])),
        int(bool(result["antecedent_hit"])),
        int(bool(result["heldout_correct_pass"])),
        int(bool(result["heldout_buggy_fail"])),
        -int(bool(result["trace_overfit"])),
        int(result.get("heldout_bad_ant_hits", 0)),
        -int(result.get("seen_good_fail_hits", 0)),
    )


def persist_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def load_existing_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    if df.empty:
        return []
    return df.to_dict(orient="records")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    case_filter = {
        item.strip()
        for item in os.environ.get("ANTREPAIR_CASE_FILTER", "").split(",")
        if item.strip()
    }
    max_cases = int(os.environ.get("ANTREPAIR_MAX_CASES", "0") or "0")
    candidate_limit = int(os.environ.get("ANTREPAIR_CANDIDATES", "5") or "5")

    selected_rows = load_selected_rows()
    if case_filter:
        selected_rows = selected_rows[selected_rows["case_id"].isin(case_filter)].copy()
    if max_cases > 0:
        selected_rows = selected_rows.head(max_cases).copy()
    if selected_rows.empty:
        raise RuntimeError("No selected repair cases remain after filtering.")

    write_text(
        OUTPUT_DIR / "selected_repair_cases.json",
        selected_rows.to_json(orient="records", force_ascii=False, indent=2),
    )

    use_property = probe_property_support(selected_rows.iloc[0]["case_id"])

    case_rows: list[dict[str, Any]] = load_existing_rows(OUTPUT_DIR / "antecedent_repair_case_summary.csv")
    result_rows: list[dict[str, Any]] = load_existing_rows(OUTPUT_DIR / "antecedent_repair_candidate_results.csv")
    prompt_rows: list[dict[str, Any]] = load_existing_rows(OUTPUT_DIR / "antecedent_repair_prompts.csv")
    completed_cases = {row["case_id"] for row in case_rows if row.get("case_id")}

    for _, row in selected_rows.iterrows():
        case_id = row["case_id"]
        if case_id in completed_cases:
            continue
        allowed_signals, spec, _rtl_text, _trace_good, _trace_bad, _trace_summary = method_context(case_id, row["prompt_type"])
        prompt_text = repair_prompt(row)
        prompt_dir = OUTPUT_DIR / "prompts" / case_id
        prompt_dir.mkdir(parents=True, exist_ok=True)
        write_text(prompt_dir / "repair_prompt.txt", prompt_text)

        original_ant, implication, consequent = split_assertion(str(row["assertion_text"]))
        original_runtime = OUTPUT_DIR / "runtime" / case_id / "original"
        original_eval = run_case_eval(
            case_id=case_id,
            assertion_text=str(row["assertion_text"]),
            signal_names=allowed_signals,
            use_property=use_property,
            runtime_dir=original_runtime,
        )

        candidates, raw_responses = collect_repair_candidates(prompt_text, case_id=case_id)
        if not candidates:
            raise RuntimeError(f"{case_id}: no repair antecedent candidates collected.")
        candidates = candidates[:candidate_limit]

        best_candidate_row: dict[str, Any] | None = None
        best_score: tuple | None = None

        for idx, antecedent_candidate in enumerate(candidates, start=1):
            repaired_assertion = build_assertion(antecedent_candidate, implication, consequent)
            runtime_dir = OUTPUT_DIR / "runtime" / case_id / f"repair_{idx:02d}"
            eval_result = run_case_eval(
                case_id=case_id,
                assertion_text=repaired_assertion,
                signal_names=allowed_signals,
                use_property=use_property,
                runtime_dir=runtime_dir,
            )
            row_out = {
                "case_id": case_id,
                "module": row["module"],
                "bug_name": row["bug_name"],
                "bug_class": row["bug_class"],
                "method": row["method"],
                "prompt_type": row["prompt_type"],
                "candidate_index": idx,
                "original_assertion": row["assertion_text"],
                "original_antecedent": original_ant,
                "locked_implication": implication,
                "locked_consequent": consequent,
                "repaired_antecedent": antecedent_candidate,
                "repaired_assertion": repaired_assertion,
                "selection_reason": row["selection_reason"],
                "trigger_condition_summary": row["trigger_condition_summary"],
                "antecedent_failure_diagnosis": row["antecedent_failure_diagnosis"],
                "original_compile_ok": original_eval["compile_ok"],
                "original_correct_pass": original_eval["correct_pass"],
                "original_fail_on_buggy": original_eval["buggy_fail"],
                "original_antecedent_hit": original_eval["antecedent_hit"],
                "original_non_vacuous": original_eval["non_vacuous"],
                "original_heldout_correct_pass": original_eval["heldout_correct_pass"],
                "original_heldout_buggy_fail": original_eval["heldout_buggy_fail"],
                "original_trace_overfit": original_eval["trace_overfit"],
                "compile_ok": eval_result["compile_ok"],
                "correct_pass": eval_result["correct_pass"],
                "fail_on_buggy": eval_result["buggy_fail"],
                "antecedent_hit": eval_result["antecedent_hit"],
                "non_vacuous": eval_result["non_vacuous"],
                "heldout_correct_pass": eval_result["heldout_correct_pass"],
                "heldout_buggy_fail": eval_result["heldout_buggy_fail"],
                "heldout_antecedent_hit": eval_result["heldout_antecedent_hit"],
                "trace_overfit": eval_result["trace_overfit"],
                "correct_pass_preserved": bool(original_eval["correct_pass"] and eval_result["correct_pass"]),
                "fail_on_buggy_improved": bool((not original_eval["buggy_fail"]) and eval_result["buggy_fail"]),
                "antecedent_hit_improved": bool((not original_eval["antecedent_hit"]) and eval_result["antecedent_hit"]),
                "false_positive_introduced": bool(original_eval["correct_pass"] and (not eval_result["correct_pass"])),
                "heldout_failure_introduced": bool(
                    (original_eval["heldout_correct_pass"] and (not eval_result["heldout_correct_pass"]))
                    or (original_eval["heldout_buggy_fail"] and (not eval_result["heldout_buggy_fail"]))
                ),
                "seen_good_ant_hits": eval_result["seen_good_ant_hits"],
                "seen_bad_ant_hits": eval_result["seen_bad_ant_hits"],
                "heldout_bad_ant_hits": eval_result["heldout_bad_ant_hits"],
                "seen_good_fail_hits": eval_result["seen_good_fail_hits"],
                "seen_bad_fail_hits": eval_result["seen_bad_fail_hits"],
                "heldout_good_fail_hits": eval_result["heldout_good_fail_hits"],
                "heldout_bad_fail_hits": eval_result["heldout_bad_fail_hits"],
                "raw_generation_responses": "\n\n===== NEXT RESPONSE =====\n\n".join(raw_responses),
            }
            result_rows.append(row_out)
            score = candidate_score(eval_result)
            if best_score is None or score > best_score:
                best_score = score
                best_candidate_row = row_out
            persist_csv(OUTPUT_DIR / "antecedent_repair_candidate_results.csv", result_rows)

        assert best_candidate_row is not None
        case_row = {
            "case_id": case_id,
            "module": row["module"],
            "bug_name": row["bug_name"],
            "bug_class": row["bug_class"],
            "method": row["method"],
            "method_label": row["method_label"],
            "prompt_type": row["prompt_type"],
            "selection_reason": row["selection_reason"],
            "trigger_condition_summary": row["trigger_condition_summary"],
            "antecedent_failure_diagnosis": row["antecedent_failure_diagnosis"],
            "original_assertion": row["assertion_text"],
            "original_antecedent": original_ant,
            "locked_implication": implication,
            "locked_consequent": consequent,
            "best_repaired_antecedent": best_candidate_row["repaired_antecedent"],
            "best_repaired_assertion": best_candidate_row["repaired_assertion"],
            "original_correct_pass": original_eval["correct_pass"],
            "repaired_correct_pass": best_candidate_row["correct_pass"],
            "original_fail_on_buggy": original_eval["buggy_fail"],
            "repaired_fail_on_buggy": best_candidate_row["fail_on_buggy"],
            "original_antecedent_hit": original_eval["antecedent_hit"],
            "repaired_antecedent_hit": best_candidate_row["antecedent_hit"],
            "original_heldout_correct_pass": original_eval["heldout_correct_pass"],
            "repaired_heldout_correct_pass": best_candidate_row["heldout_correct_pass"],
            "original_heldout_buggy_fail": original_eval["heldout_buggy_fail"],
            "repaired_heldout_buggy_fail": best_candidate_row["heldout_buggy_fail"],
            "correct_pass_preserved": best_candidate_row["correct_pass_preserved"],
            "fail_on_buggy_improved": best_candidate_row["fail_on_buggy_improved"],
            "antecedent_hit_improved": best_candidate_row["antecedent_hit_improved"],
            "false_positive_introduced": best_candidate_row["false_positive_introduced"],
            "heldout_failure_introduced": best_candidate_row["heldout_failure_introduced"],
            "best_candidate_index": best_candidate_row["candidate_index"],
            "generated_candidate_count": len(candidates),
        }
        case_rows.append(case_row)
        prompt_rows.append(
            {
                "case_id": case_id,
                "module": row["module"],
                "bug_name": row["bug_name"],
                "method": row["method"],
                "prompt_type": row["prompt_type"],
                "repair_prompt_path": str((prompt_dir / "repair_prompt.txt").resolve()),
                "repair_prompt_text": prompt_text,
                "original_assertion": row["assertion_text"],
                "best_repaired_assertion": best_candidate_row["repaired_assertion"],
                "generated_candidate_count": len(candidates),
            }
        )
        persist_csv(OUTPUT_DIR / "antecedent_repair_case_summary.csv", case_rows)
        persist_csv(OUTPUT_DIR / "antecedent_repair_prompts.csv", prompt_rows)
        completed_cases.add(case_id)

    summary = {
        "model_name": MODEL_NAME,
        "ollama_url": OLLAMA_URL,
        "selected_case_count": len(case_rows),
        "candidate_limit_per_case": candidate_limit,
        "use_property_compile_mode": use_property,
        "case_filter": sorted(case_filter),
        "max_cases": max_cases,
        "argv": sys.argv,
    }
    write_text(OUTPUT_DIR / "antecedent_repair_run_meta.json", json.dumps(summary, indent=2, ensure_ascii=False))
    print(OUTPUT_DIR / "antecedent_repair_case_summary.csv")
    print(OUTPUT_DIR / "antecedent_repair_candidate_results.csv")
    print(OUTPUT_DIR / "antecedent_repair_prompts.csv")


if __name__ == "__main__":
    main()
