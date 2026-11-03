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

from run_trace_abstraction_prototype import (  # noqa: E402
    CASES_ROOT,
    MODEL_NAME,
    OLLAMA_URL,
    extract_rtl_from_prompt,
    extract_sva_candidates,
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
SOURCE_SELECTED_CASES = ROOT / "outputs" / THREAD_ID / "trace_abstraction_data" / "selected_cases.json"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "prompt_ablation_data"


PROMPT_VARIANTS: list[dict[str, str]] = [
    {
        "prompt_variant": "control_no_avoid_hardcoding",
        "constraint_family": "control",
        "constraint_focus": "No explicit anti-hardcoding reminder. Use this as the neutral baseline.",
        "extra_instruction": "",
    },
    {
        "prompt_variant": "remind_avoid_hardcoding",
        "constraint_family": "hardcoding",
        "constraint_focus": "Explicitly remind the model not to pin trace literals unless the spec/RTL justifies them.",
        "extra_instruction": (
            "Focus instruction: avoid hardcoding observed literals from the seen trace "
            "unless the spec or RTL independently justifies them."
        ),
    },
    {
        "prompt_variant": "remind_antecedent_must_trigger",
        "constraint_family": "vacuity",
        "constraint_focus": "Explicitly remind the model that the antecedent must really trigger on the bug-revealing scenario.",
        "extra_instruction": (
            "Focus instruction: make sure the antecedent actually triggers on the bug-revealing buggy trace; "
            "avoid vacuous antecedents that never fire."
        ),
    },
    {
        "prompt_variant": "remind_use_temporal_operator",
        "constraint_family": "temporal_operator",
        "constraint_focus": "Explicitly remind the model to use temporal structure when the relation crosses cycles.",
        "extra_instruction": (
            "Focus instruction: if the relation crosses cycles, prefer a temporal formulation such as |=>; "
            "you may use $past(<allowed_signal>) when it genuinely helps express the timing dependency."
        ),
    },
    {
        "prompt_variant": "remind_pass_correct_fail_buggy",
        "constraint_family": "objective",
        "constraint_focus": "Explicitly remind the model to target pass-on-correct and fail-on-buggy simultaneously.",
        "extra_instruction": (
            "Focus instruction: prefer candidates that pass on correct behavior and fail on buggy behavior."
        ),
    },
    {
        "prompt_variant": "remind_heldout_generalization",
        "constraint_family": "generalization",
        "constraint_focus": "Explicitly remind the model to generalize beyond the seen trace to held-out traces.",
        "extra_instruction": (
            "Focus instruction: prefer relations that should still hold on held-out traces rather than only matching the seen trace."
        ),
    },
]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def sanitize_abstracted_summary(summary_text: str) -> str:
    kept_lines = []
    for raw_line in str(summary_text or "").splitlines():
        line = raw_line.rstrip()
        low = line.lower()
        if "do not hardcode" in low:
            continue
        if "avoid hardcoding" in low:
            continue
        if line.strip().startswith("- Preserve the relation"):
            continue
        if line.strip().startswith("- Preserve the cross-cycle relation"):
            continue
        if line.strip().startswith("- Preserve the same-cycle"):
            continue
        if line.strip().startswith("- Preserve the boundary relation"):
            continue
        kept_lines.append(line)
    cleaned = "\n".join([line for line in kept_lines if line.strip()]).strip()
    return cleaned


def collect_candidates(prompt: str, *, target_count: int) -> tuple[list[str], list[str]]:
    collected: list[str] = []
    raw_responses: list[str] = []
    temperatures = [0.6, 0.8, 1.0]
    for temp in temperatures:
        attempt_prompt = prompt
        if collected:
            attempt_prompt += "\n\nDo not repeat previous candidates:\n- " + "\n- ".join(collected)
        response = post_ollama(attempt_prompt, temperature=temp)
        raw_responses.append(response)
        for candidate in extract_sva_candidates(response):
            if candidate not in collected:
                collected.append(candidate)
            if len(collected) >= target_count:
                return collected[:target_count], raw_responses
    return collected[:target_count], raw_responses


def literal_hardcoding_flag(assertion_text: str) -> bool:
    text = str(assertion_text or "")
    hits = re.findall(r"\b(\d+)'[bdho][0-9a-fA-F_xzXZ?]+\b", text)
    for width in hits:
        pass
    literal_tokens = re.findall(r"\b\d+'[bdho][0-9a-fA-F_xzXZ?]+\b|\b\d+\b", text)
    for tok in literal_tokens:
        low = tok.lower()
        if low in {"0", "1", "1'b0", "1'b1", "1'd0", "1'd1", "1'h0", "1'h1"}:
            continue
        return True
    return False


def uses_temporal_feature(assertion_text: str) -> bool:
    text = str(assertion_text or "")
    return ("|=>" in text) or ("$past(" in text)


def failed_eval_result(reason: str) -> dict[str, Any]:
    return {
        "compile_ok": False,
        "correct_pass": False,
        "buggy_fail": False,
        "antecedent_hit": False,
        "non_vacuous": False,
        "heldout_correct_pass": False,
        "heldout_buggy_fail": False,
        "heldout_antecedent_hit": False,
        "heldout_non_vacuous": False,
        "trace_overfit": False,
        "seen_good_ant_hits": 0,
        "seen_bad_ant_hits": 0,
        "heldout_bad_ant_hits": 0,
        "seen_good_fail_hits": 0,
        "seen_bad_fail_hits": 0,
        "heldout_good_fail_hits": 0,
        "heldout_bad_fail_hits": 0,
        "compile_stderr_seen_good": reason,
        "compile_stderr_seen_bad": reason,
        "compile_stderr_holdout_good": reason,
        "compile_stderr_holdout_bad": reason,
    }


def make_generation_prompt(
    *,
    allowed_signals: list[str],
    spec: str,
    rtl_text: str,
    abstracted_summary: str,
    additional_guidance: str,
    extra_instruction: str,
) -> str:
    guidance_block = f"\nAdditional guidance:\n{additional_guidance}\n" if additional_guidance else ""
    extra_block = f"\n{extra_instruction}\n" if extra_instruction else "\n"
    return textwrap.dedent(
        f"""
        You are a formal verification engineer.
        Generate exactly five distinct SystemVerilog Assertions in this strict format, one assertion per line:
        assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));

        Core rules:
        1) Output exactly five assertion lines total. No explanation. No markdown. No numbering.
        2) Use only allowed signals listed below.
        3) Each candidate must contain exactly one implication operator total: either one |-> or one |=>.
        4) Use only a single assertion per line. No helper/internal names such as next_state, count_next, count_prev, old(...), S_*.
        5) Keep the five candidates meaningfully different while staying semantically faithful to the spec and the abstracted trace evidence.
        6) For non-temporal cases, stay with simple cycle-local logic unless cross-cycle reasoning is clearly needed.
        7) Avoid gratuitous complexity: use the strongest concise assertion you can justify.
        {extra_block}
        Allowed signals:
        {", ".join(allowed_signals)}

        Specification:
        {spec}
        {guidance_block}
        RTL:
        {rtl_text}

        Abstracted trace summary:
        {abstracted_summary}
        """
    ).strip()


def load_case_bundles() -> list[dict[str, Any]]:
    selected_cases = json.loads(SOURCE_SELECTED_CASES.read_text(encoding="utf-8"))
    bundles: list[dict[str, Any]] = []
    for item in selected_cases:
        case_id = item["case_id"]
        case_dir = CASES_ROOT / case_id / "experiment"
        raw_prompt_src = read_text(case_dir / "prompts" / "prompt_3_spec_rtl_raw_trace.txt")
        bundles.append(
            {
                "case_id": case_id,
                "selection_tags": item.get("selection_tags", ""),
                "selection_reason": item.get("selection_reason", ""),
                "spec": item["spec"],
                "abstracted_trace_summary_original": item["abstracted_trace_summary"],
                "abstracted_trace_summary_sanitized": sanitize_abstracted_summary(item["abstracted_trace_summary"]),
                "allowed_signals": parse_allowed_signals(raw_prompt_src),
                "rtl_text": extract_rtl_from_prompt(raw_prompt_src),
                "additional_guidance": extract_waveform_guidance(raw_prompt_src),
            }
        )
    return bundles


def persist_progress(
    prompt_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]] | None = None,
) -> None:
    if prompt_rows:
        pd.DataFrame(prompt_rows).to_csv(
            OUTPUT_DIR / "prompt_ablation_prompt_design.csv",
            index=False,
            encoding="utf-8-sig",
        )
    if result_rows:
        pd.DataFrame(result_rows).to_csv(
            OUTPUT_DIR / "prompt_ablation_results_raw.csv",
            index=False,
            encoding="utf-8-sig",
        )
    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(
            OUTPUT_DIR / "prompt_ablation_summary_by_prompt.csv",
            index=False,
            encoding="utf-8-sig",
        )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    case_filter = {
        item.strip()
        for item in os.environ.get("PROMPTABL_CASE_FILTER", "").split(",")
        if item.strip()
    }
    prompt_filter = {
        item.strip()
        for item in os.environ.get("PROMPTABL_PROMPT_FILTER", "").split(",")
        if item.strip()
    }
    max_cases = int(os.environ.get("PROMPTABL_MAX_CASES", "0") or "0")
    candidates_per_prompt = int(os.environ.get("PROMPTABL_CANDIDATES_PER_PROMPT", "5") or "5")

    bundles = load_case_bundles()
    if case_filter:
        bundles = [item for item in bundles if item["case_id"] in case_filter]
    if max_cases > 0:
        bundles = bundles[:max_cases]
    if not bundles:
        raise RuntimeError("No cases selected after PROMPTABL_CASE_FILTER / PROMPTABL_MAX_CASES.")

    prompt_variants = [item for item in PROMPT_VARIANTS if (not prompt_filter or item["prompt_variant"] in prompt_filter)]
    if not prompt_variants:
        raise RuntimeError("No prompt variants selected after PROMPTABL_PROMPT_FILTER.")

    use_property = probe_property_support(bundles[0]["case_id"])

    prompt_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    existing_path = OUTPUT_DIR / "prompt_ablation_results_raw.csv"
    if existing_path.exists():
        existing_df = pd.read_csv(existing_path)
        if not existing_df.empty:
            result_rows = existing_df.to_dict(orient="records")

    for bundle in bundles:
        case_id = bundle["case_id"]
        prompt_dir = OUTPUT_DIR / "prompts" / case_id
        prompt_dir.mkdir(parents=True, exist_ok=True)
        for variant in prompt_variants:
            prompt_text = make_generation_prompt(
                allowed_signals=bundle["allowed_signals"],
                spec=bundle["spec"],
                rtl_text=bundle["rtl_text"],
                abstracted_summary=bundle["abstracted_trace_summary_sanitized"],
                additional_guidance=bundle["additional_guidance"],
                extra_instruction=variant["extra_instruction"],
            )
            prompt_path = prompt_dir / f"{variant['prompt_variant']}.txt"
            write_text(prompt_path, prompt_text)
            prompt_rows.append(
                {
                    "case_id": case_id,
                    "prompt_variant": variant["prompt_variant"],
                    "constraint_family": variant["constraint_family"],
                    "constraint_focus": variant["constraint_focus"],
                    "selection_tags": bundle["selection_tags"],
                    "selection_reason": bundle["selection_reason"],
                    "spec": bundle["spec"],
                    "abstracted_trace_summary_original": bundle["abstracted_trace_summary_original"],
                    "abstracted_trace_summary_sanitized": bundle["abstracted_trace_summary_sanitized"],
                    "extra_instruction": variant["extra_instruction"],
                    "prompt_path": str(prompt_path.resolve()),
                }
            )

            existing_variant_rows = [
                row
                for row in result_rows
                if row.get("case_id") == case_id and row.get("prompt_variant") == variant["prompt_variant"]
            ]
            if len(existing_variant_rows) >= candidates_per_prompt:
                persist_progress(prompt_rows, result_rows)
                continue
            if 0 < len(existing_variant_rows) < candidates_per_prompt:
                result_rows = [
                    row
                    for row in result_rows
                    if not (row.get("case_id") == case_id and row.get("prompt_variant") == variant["prompt_variant"])
                ]

            candidates, raw_responses = collect_candidates(prompt_text, target_count=candidates_per_prompt)
            candidates = candidates[:candidates_per_prompt]
            if len(candidates) < candidates_per_prompt:
                raise RuntimeError(
                    f"{case_id}/{variant['prompt_variant']}: only collected {len(candidates)} candidates."
                )
            judge_map = judge_semantic_reasonable(
                spec=bundle["spec"],
                case_id=case_id,
                candidates=candidates,
            )

            for candidate_idx, assertion_text in enumerate(candidates, start=1):
                runtime_dir = OUTPUT_DIR / "runtime" / case_id / variant["prompt_variant"] / f"cand_{candidate_idx:02d}"
                try:
                    eval_result = run_case_eval(
                        case_id=case_id,
                        assertion_text=assertion_text,
                        signal_names=bundle["allowed_signals"],
                        use_property=use_property,
                        runtime_dir=runtime_dir,
                    )
                except Exception as exc:
                    eval_result = failed_eval_result(f"run_case_eval_error: {exc}")
                judge_info = judge_map.get(
                    str(candidate_idx),
                    {"semantic_reasonable": False, "semantic_reason": "judge_missing"},
                )
                strict_success = bool(
                    eval_result["compile_ok"]
                    and eval_result["correct_pass"]
                    and eval_result["buggy_fail"]
                    and eval_result["heldout_correct_pass"]
                    and eval_result["heldout_buggy_fail"]
                    and eval_result["heldout_antecedent_hit"]
                )
                heldout_success = bool(
                    eval_result["compile_ok"]
                    and eval_result["heldout_correct_pass"]
                    and eval_result["heldout_buggy_fail"]
                )
                result_rows.append(
                    {
                        "case_id": case_id,
                        "selection_tags": bundle["selection_tags"],
                        "prompt_variant": variant["prompt_variant"],
                        "constraint_family": variant["constraint_family"],
                        "constraint_focus": variant["constraint_focus"],
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
                        "literal_hardcoding": literal_hardcoding_flag(assertion_text),
                        "uses_temporal_feature": uses_temporal_feature(assertion_text),
                        "strict_success": strict_success,
                        "heldout_success": heldout_success,
                        "seen_good_ant_hits": eval_result["seen_good_ant_hits"],
                        "seen_bad_ant_hits": eval_result["seen_bad_ant_hits"],
                        "heldout_bad_ant_hits": eval_result["heldout_bad_ant_hits"],
                        "seen_good_fail_hits": eval_result["seen_good_fail_hits"],
                        "seen_bad_fail_hits": eval_result["seen_bad_fail_hits"],
                        "heldout_good_fail_hits": eval_result["heldout_good_fail_hits"],
                        "heldout_bad_fail_hits": eval_result["heldout_bad_fail_hits"],
                        "use_property_compile_mode": use_property,
                        "raw_generation_responses": "\n\n===== NEXT RESPONSE =====\n\n".join(raw_responses),
                    }
                )
                persist_progress(prompt_rows, result_rows)

    result_df = pd.DataFrame(result_rows).sort_values(
        ["prompt_variant", "case_id", "candidate_index"]
    ).reset_index(drop=True)
    result_df.to_csv(OUTPUT_DIR / "prompt_ablation_results_raw.csv", index=False, encoding="utf-8-sig")

    prompt_df = pd.DataFrame(prompt_rows).drop_duplicates(
        subset=["case_id", "prompt_variant"]
    ).sort_values(["prompt_variant", "case_id"]).reset_index(drop=True)
    prompt_df.to_csv(OUTPUT_DIR / "prompt_ablation_prompt_design.csv", index=False, encoding="utf-8-sig")

    prompt_summary_rows = []
    for prompt_variant, sub in result_df.groupby("prompt_variant", dropna=False):
        prompt_summary_rows.append(
            {
                "prompt_variant": prompt_variant,
                "constraint_family": sub["constraint_family"].iloc[0],
                "candidate_count": int(len(sub)),
                "case_count": int(sub["case_id"].nunique()),
                "compile_ok_rate": float(sub["compile_ok"].mean()),
                "correct_pass_rate": float(sub["correct_pass"].mean()),
                "buggy_fail_rate": float(sub["buggy_fail"].mean()),
                "antecedent_hit_rate": float(sub["antecedent_hit"].mean()),
                "non_vacuous_rate": float(sub["non_vacuous"].mean()),
                "heldout_correct_pass_rate": float(sub["heldout_correct_pass"].mean()),
                "heldout_buggy_fail_rate": float(sub["heldout_buggy_fail"].mean()),
                "heldout_antecedent_hit_rate": float(sub["heldout_antecedent_hit"].mean()),
                "heldout_success_rate": float(sub["heldout_success"].mean()),
                "strict_success_rate": float(sub["strict_success"].mean()),
                "trace_overfit_rate": float(sub["trace_overfit"].mean()),
                "literal_hardcoding_rate": float(sub["literal_hardcoding"].mean()),
                "semantic_reasonable_rate": float(sub["semantic_reasonable"].mean()),
                "uses_temporal_feature_rate": float(sub["uses_temporal_feature"].mean()),
                "strict_success_case_count": int(
                    sub.groupby("case_id", dropna=False)["strict_success"].max().sum()
                ),
                "heldout_success_case_count": int(
                    sub.groupby("case_id", dropna=False)["heldout_success"].max().sum()
                ),
            }
        )
    prompt_summary_df = pd.DataFrame(prompt_summary_rows).sort_values(
        [
            "strict_success_rate",
            "heldout_success_rate",
            "buggy_fail_rate",
            "correct_pass_rate",
        ],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    prompt_summary_df.to_csv(
        OUTPUT_DIR / "prompt_ablation_summary_by_prompt.csv",
        index=False,
        encoding="utf-8-sig",
    )

    case_prompt_rows = []
    for (case_id, prompt_variant), sub in result_df.groupby(["case_id", "prompt_variant"], dropna=False):
        case_prompt_rows.append(
            {
                "case_id": case_id,
                "prompt_variant": prompt_variant,
                "constraint_family": sub["constraint_family"].iloc[0],
                "candidate_count": int(len(sub)),
                "compile_ok_rate": float(sub["compile_ok"].mean()),
                "correct_pass_rate": float(sub["correct_pass"].mean()),
                "buggy_fail_rate": float(sub["buggy_fail"].mean()),
                "antecedent_hit_rate": float(sub["antecedent_hit"].mean()),
                "heldout_success_rate": float(sub["heldout_success"].mean()),
                "strict_success_rate": float(sub["strict_success"].mean()),
                "trace_overfit_rate": float(sub["trace_overfit"].mean()),
                "literal_hardcoding_rate": float(sub["literal_hardcoding"].mean()),
                "uses_temporal_feature_rate": float(sub["uses_temporal_feature"].mean()),
                "best_assertion_text": next(
                    iter(
                        sub.sort_values(
                            [
                                "strict_success",
                                "heldout_success",
                                "buggy_fail",
                                "correct_pass",
                                "antecedent_hit",
                                "semantic_reasonable",
                            ],
                            ascending=[False, False, False, False, False, False],
                        )["assertion_text"].tolist()
                    ),
                    "",
                ),
            }
        )
    case_prompt_df = pd.DataFrame(case_prompt_rows).sort_values(
        ["case_id", "prompt_variant"]
    ).reset_index(drop=True)
    case_prompt_df.to_csv(
        OUTPUT_DIR / "prompt_ablation_case_prompt_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    write_text(
        OUTPUT_DIR / "prompt_ablation_run_meta.json",
        json.dumps(
            {
                "model_name": MODEL_NAME,
                "ollama_url": OLLAMA_URL,
                "selected_case_count": len(bundles),
                "prompt_variants": [item["prompt_variant"] for item in prompt_variants],
                "candidates_per_prompt": candidates_per_prompt,
                "use_property_compile_mode": use_property,
                "case_filter": sorted(case_filter),
                "prompt_filter": sorted(prompt_filter),
                "max_cases": max_cases,
                "notes": [
                    "The original abstracted summaries were sanitized by removing the final anti-hardcoding/preserve-relation instruction line.",
                    "This keeps prompt ablation focused on the prompt constraint itself rather than duplicated guidance inside the summary payload.",
                ],
                "argv": sys.argv,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )

    print(OUTPUT_DIR / "prompt_ablation_results_raw.csv")
    print(OUTPUT_DIR / "prompt_ablation_summary_by_prompt.csv")
    print(OUTPUT_DIR / "prompt_ablation_case_prompt_summary.csv")


if __name__ == "__main__":
    main()
