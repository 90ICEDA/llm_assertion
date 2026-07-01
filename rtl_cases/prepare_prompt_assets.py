#!/usr/bin/env python3
import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List

from summarize_trace_divergence import summarize_case, build_text_summary


PROMPT_SPEC_ONLY = """You are a formal verification engineer.
Generate exactly one SystemVerilog Assertion in this strict format:
assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));

Rules:
1) Output only one assertion line. No explanation. No markdown.
2) Use only allowed signals listed below.
3) Keep antecedent and consequent purely boolean (no ##, no $past, no sequence operators).
4) No helper/internal names such as next_state, count_next, count_prev, old(...), S_*.
5) Do not concatenate multiple assertions. Exactly one assert property statement.
6) For register-update behavior, prefer next-cycle implication (|=>) instead of same-cycle check.
7) Target a meaningful safety property (not vacuous).
8) Internal RTL names may appear below for understanding only. Never reference any name that is not in Allowed signals.
9) If the full intent cannot be expressed under these restrictions, emit the strongest single implication over Allowed signals that still captures the bug.
10) The final assertion line must contain exactly one implication operator total: either one |-> or one |=>.

Allowed signals:
{allowed_signals}

Specification:
{spec}

Additional guidance:
{extra_guidance}
"""

PROMPT_SPEC_RTL = """You are a formal verification engineer.
Generate exactly one SystemVerilog Assertion in this strict format:
assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));

Rules:
1) Output only one assertion line. No explanation. No markdown.
2) Use only allowed signals listed below.
3) Keep antecedent and consequent purely boolean (no ##, no $past, no sequence operators).
4) No helper/internal names such as next_state, count_next, count_prev, old(...), S_*.
5) Do not concatenate multiple assertions. Exactly one assert property statement.
6) For register-update behavior, prefer next-cycle implication (|=>) instead of same-cycle check.
7) Target a meaningful safety property (not vacuous).
8) Internal RTL names may appear below for understanding only. Never reference any name that is not in Allowed signals.
9) If the full intent cannot be expressed under these restrictions, emit the strongest single implication over Allowed signals that still captures the bug.
10) The final assertion line must contain exactly one implication operator total: either one |-> or one |=>.

Allowed signals:
{allowed_signals}

Specification:
{spec}

Additional guidance:
{extra_guidance}

RTL:
{rtl}
"""

PROMPT_SPEC_RTL_RAW_TRACE = """You are a formal verification engineer.
Generate exactly one SystemVerilog Assertion in this strict format:
assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));

Rules:
1) Output only one assertion line. No explanation. No markdown.
2) Use only allowed signals listed below.
3) Keep antecedent and consequent purely boolean (no ##, no $past, no sequence operators).
4) No helper/internal names such as next_state, count_next, count_prev, old(...), S_*.
5) Do not concatenate multiple assertions. Exactly one assert property statement.
6) For register-update behavior, prefer next-cycle implication (|=>) instead of same-cycle check.
7) The assertion should pass on good behavior and fail on bad behavior.
8) Avoid vacuous antecedent: choose a condition that appears in traces.
9) Internal RTL names may appear below for understanding only. Never reference any name that is not in Allowed signals.
10) If the full intent cannot be expressed under these restrictions, emit the strongest single implication over Allowed signals that still distinguishes good and bad traces.
11) The final assertion line must contain exactly one implication operator total: either one |-> or one |=>.
12) Use the traces to infer a general relation, not to memorize one witnessed cycle.
13) Do not hard-code trace-only multi-bit values or one-off transitions such as a single observed address pair unless the value is explicitly justified by the spec or RTL.

Allowed signals:
{allowed_signals}

Specification:
{spec}

Additional guidance:
{extra_guidance}

RTL:
{rtl}

Good trace (posedge cycles):
{good_trace}

Bad trace (posedge cycles):
{bad_trace}
"""

PROMPT_SPEC_RTL_TRACE_SUMMARY = """You are a formal verification engineer.
Generate exactly one SystemVerilog Assertion in this strict format:
assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));

Rules:
1) Output only one assertion line. No explanation. No markdown.
2) Use only allowed signals listed below.
3) Keep antecedent and consequent purely boolean (no ##, no $past, no sequence operators).
4) No helper/internal names such as next_state, count_next, count_prev, old(...), S_*.
5) Do not concatenate multiple assertions. Exactly one assert property statement.
6) For register-update behavior, prefer next-cycle implication (|=>) instead of same-cycle check.
7) The assertion should pass on good behavior and fail on bad behavior.
8) Avoid vacuous antecedent: choose a condition that appears in traces.
9) Internal RTL names may appear below for understanding only. Never reference any name that is not in Allowed signals.
10) If the full intent cannot be expressed under these restrictions, emit the strongest single implication over Allowed signals that still distinguishes good and bad traces.
11) The final assertion line must contain exactly one implication operator total: either one |-> or one |=>.
12) Treat the trace divergence summary as observational evidence only.
13) Infer a general relation from the divergence; do not hard-code one observed trace value or one observed transition unless the value is explicitly justified by the spec or RTL.
14) If "First divergence cycle" is "none", fall back to the strongest RTL/spec-based property you can express with allowed signals.

Allowed signals:
{allowed_signals}

Specification:
{spec}

Additional guidance:
{extra_guidance}

RTL:
{rtl}

Trace divergence summary:
{trace_summary}

Summary-driven construction checklist:
- Identify the first divergence cycle and the listed differing signal(s).
- Treat the differing signal(s) as candidate consequent targets.
- Use the observed divergence to infer a reusable rule rather than a one-off constant match.
- Choose an antecedent that is actually observed in traces and is as specific as needed to separate good from bad.
- Avoid consequents that simply restate reset-high, rst_n, or another trivially satisfied condition.
- Do not copy concrete multi-bit values from the summary directly into the assertion unless the spec or RTL independently justifies them.
"""


def read_manifest(root: Path) -> List[Dict]:
    manifest_path = root / "case_manifest.json"
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)["cases"]


def read_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_rising_edge(prev_clk: str, curr_clk: str) -> bool:
    return prev_clk == "0" and curr_clk == "1"


def signal_base_name(name: str) -> str:
    return re.sub(r"\[.*\]$", "", name)


def resolve_selected_signals(key_signals: List[str], columns: List[str]) -> List[str]:
    resolved: List[str] = []
    for key in key_signals:
        match = None
        if key in columns:
            match = key
        else:
            for col in columns:
                if signal_base_name(col) == key:
                    match = col
                    break
        if match and match not in resolved:
            resolved.append(match)
    return resolved


def to_cycle_trace(rows: List[Dict[str, str]], key_signals: List[str]) -> List[Dict[str, str]]:
    if not rows:
        return []

    keys = list(rows[0].keys())
    key_set = set(keys)
    has_clk = "clk" in keys
    selected = resolve_selected_signals(key_signals, keys)
    if "clk" in key_set and "clk" not in selected:
        selected = ["clk"] + selected
    if "rst_n" in key_set and "rst_n" not in selected:
        selected = ["rst_n"] + selected

    out = []
    cycle = 0

    if has_clk:
        prev = rows[0].get("clk", "0")
        for i in range(1, len(rows)):
            curr = rows[i].get("clk", "0")
            if is_rising_edge(prev, curr):
                entry = {"cycle": str(cycle)}
                for s in selected:
                    entry[s] = rows[i].get(s, "")
                out.append(entry)
                cycle += 1
            prev = curr
    else:
        for r in rows:
            entry = {"cycle": str(cycle)}
            for s in selected:
                entry[s] = r.get(s, "")
            out.append(entry)
            cycle += 1
    return out


def format_trace_text(cycle_rows: List[Dict[str, str]]) -> str:
    if not cycle_rows:
        return "(empty)"
    sigs = [k for k in cycle_rows[0].keys() if k != "cycle"]
    lines = []
    for row in cycle_rows:
        pairs = [f"{s}={row[s]}" for s in sigs]
        lines.append(f"cycle {row['cycle']}: " + ", ".join(pairs))
    return "\n".join(lines)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def maybe_write_holdout_trace_text(
    case_dir: Path,
    exp_dir: Path,
    key_signals: List[str],
) -> None:
    holdout_pairs = [
        ("waveform_good_holdout.csv", "trace_good_holdout.txt"),
        ("waveform_bad_holdout.csv", "trace_bad_holdout.txt"),
    ]
    for csv_name, out_name in holdout_pairs:
        csv_path = case_dir / csv_name
        if not csv_path.exists():
            continue
        rows = read_csv_rows(csv_path)
        cycle_rows = to_cycle_trace(rows, key_signals)
        write_text(exp_dir / out_name, format_trace_text(cycle_rows) + "\n")


def build_structured_trace_summary(summary: Dict) -> str:
    first_div = summary.get("first_divergence_cycle")
    differing = summary.get("differing_signals") or []
    snapshot = summary.get("divergence_snapshot") or []
    lines = [
        "Structured trace summary:",
        f"- first_divergence_cycle: {'none' if first_div is None else first_div}",
        "- differing_signals: " + (", ".join(differing) if differing else "(none)"),
    ]
    if snapshot:
        lines.append("- divergence_snapshot:")
        for item in snapshot:
            lines.append(
                f"  - {item.get('signal', '')}: good={item.get('good', '')}, "
                f"bad={item.get('bad', '')}"
            )
    else:
        lines.append("- divergence_snapshot: (none)")
    return "\n".join(lines)


def build_extra_guidance(case_meta: Dict, rtl_text: str, good_rows: List[Dict[str, str]]) -> str:
    hints: List[str] = []
    allowed = set(case_meta["key_signals"])
    case_name = case_meta.get("name", "")

    columns = list(good_rows[0].keys()) if good_rows else []
    alias_hints: List[str] = []
    for col in columns:
        base = signal_base_name(col)
        if base in allowed and col != base:
            alias_hints.append(f"{base} appears in waveforms as column '{col}'")
    if alias_hints:
        hints.append("Waveform naming hints: " + "; ".join(alias_hints) + ".")

    if "state" in allowed:
        localparams = re.findall(r"localparam\s+([A-Za-z_]\w*)\s*=\s*([^;]+);", rtl_text)
        state_params = [
            f"{name}={value.strip()}"
            for name, value in localparams
            if name.startswith("S_")
        ]
        if state_params:
            hints.append(
                "Use numeric comparisons on state in the final assertion, not symbolic names: "
                + ", ".join(state_params)
                + "."
            )

    internal_regs = [
        reg_name
        for reg_name in re.findall(r"\breg\b(?:\s*\[[^\]]+\])?\s+([A-Za-z_]\w*)", rtl_text)
        if reg_name not in allowed
    ]
    if internal_regs:
        hints.append(
            "These RTL internals are not legal in the assertion and must never be referenced: "
            + ", ".join(sorted(set(internal_regs)))
            + "."
        )

    if case_name == "case08_pulse_width":
        hints.append(
            "pulse is a 1-bit scalar, so never write pulse[0], pulse[1], pulse[2], or any other bit/part select on pulse."
        )
        hints.append(
            "Do not use event controls such as @(posedge clk) inside antecedent or consequent; the only clock event is the outer assert property wrapper."
        )
        hints.append(
            "With the allowed signals only, a valid single-implication approximation is of the form '(trigger) |=> (pulse)'."
        )

    if case_name == "case03_valid_ready_or_bug":
        hints.append(
            "A strong legal form for this bug is to detect one-sided handshakes and require valid_o to stay low, for example using only valid_i, ready_i, and valid_o."
        )

    if not hints:
        hints.append("Use only the allowed interface-visible signals in the final assertion.")
    return "\n".join(f"- {hint}" for hint in hints)


def main():
    parser = argparse.ArgumentParser(
        description="Generate per-cycle trace text and 4 prompt variants for rtl_cases."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Path to rtl_cases root directory (default: current directory).",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cases = read_manifest(root)

    for c in cases:
        case_dir = root / c["name"]
        exp_dir = case_dir / "experiment"
        prompts_dir = exp_dir / "prompts"

        rtl_text = (case_dir / "correct.v").read_text(encoding="utf-8")
        good_rows = read_csv_rows(case_dir / "waveform_good.csv")
        bad_rows = read_csv_rows(case_dir / "waveform_bad.csv")

        good_cycle = to_cycle_trace(good_rows, c["key_signals"])
        bad_cycle = to_cycle_trace(bad_rows, c["key_signals"])

        good_trace = format_trace_text(good_cycle)
        bad_trace = format_trace_text(bad_cycle)
        allowed_signals = ", ".join(c["key_signals"])
        extra_guidance = build_extra_guidance(c, rtl_text, good_rows)
        summary = summarize_case(root, c)
        trace_summary = build_text_summary(
            c,
            summary["first_divergence_cycle"],
            summary["differing_signals"],
            summary["divergence_snapshot"],
        )
        structured_trace_summary = build_structured_trace_summary(summary)

        write_text(exp_dir / "spec.txt", c["spec"] + "\n")
        write_text(exp_dir / "trace_good.txt", good_trace + "\n")
        write_text(exp_dir / "trace_bad.txt", bad_trace + "\n")
        maybe_write_holdout_trace_text(case_dir, exp_dir, c["key_signals"])
        write_text(exp_dir / "trace_summary.txt", trace_summary + "\n")
        write_text(
            exp_dir / "trace_summary.json",
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        )

        p1 = PROMPT_SPEC_ONLY.format(
            spec=c["spec"],
            allowed_signals=allowed_signals,
            extra_guidance=extra_guidance,
        )
        p2 = PROMPT_SPEC_RTL.format(
            spec=c["spec"],
            rtl=rtl_text,
            allowed_signals=allowed_signals,
            extra_guidance=extra_guidance,
        )
        p3 = PROMPT_SPEC_RTL_RAW_TRACE.format(
            spec=c["spec"],
            rtl=rtl_text,
            good_trace=good_trace,
            bad_trace=bad_trace,
            allowed_signals=allowed_signals,
            extra_guidance=extra_guidance,
        )
        p4 = PROMPT_SPEC_RTL_TRACE_SUMMARY.format(
            spec=c["spec"],
            rtl=rtl_text,
            trace_summary=trace_summary + "\n\n" + structured_trace_summary,
            allowed_signals=allowed_signals,
            extra_guidance=extra_guidance,
        )

        write_text(prompts_dir / "prompt_1_spec_only.txt", p1)
        write_text(prompts_dir / "prompt_2_spec_plus_rtl.txt", p2)
        write_text(prompts_dir / "prompt_3_spec_rtl_raw_trace.txt", p3)
        write_text(prompts_dir / "prompt_4_spec_rtl_trace_summary.txt", p4)

        print(f"[OK] Prepared assets for {c['name']}")


if __name__ == "__main__":
    main()
