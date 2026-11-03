#!/usr/bin/env python3
"""Materialize deliberately weak SVA candidates for common_cells scale210 cases.

This script creates candidates only.  It intentionally does not claim that any
candidate has passed compilation, non-vacuity, or correct/buggy discrimination.
Those fields remain pending until the separate WSL validation gate is run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "rtl_cases_real_scale210_independent"


def base(signal: str) -> str:
    return re.sub(r"\[[^]]+\]$", "", signal)


def choose_signals(meta: dict) -> tuple[str | None, str | None, str, str]:
    signals = [base(s) for s in meta["relevant_signals"]]
    clock = next((s for s in signals if s.startswith("clk") or "clk_" in s), None)
    reset = next((s for s in signals if "rst" in s), None)
    excluded = {clock, reset}
    inputs = [s for s in signals if s not in excluded and (s.endswith("_i") or "_i" in s)]
    outputs = [s for s in signals if s not in excluded and (s.endswith("_o") or "_o" in s)]
    trigger = inputs[0] if inputs else next(s for s in signals if s not in excluded)
    observed = outputs[-1] if outputs else next(s for s in reversed(signals) if s not in excluded)
    return clock, reset, trigger, observed


def sampled(clock: str | None, reset: str | None, body: str) -> str:
    if clock:
        disable = f" disable iff (!{reset})" if reset and reset.endswith("_ni") else ""
        return f"assert property (@(posedge {clock}){disable} {body});"
    return f"assert property (@(*) {body});"


def build(meta: dict) -> list[dict]:
    clock, reset, trigger, observed = choose_signals(meta)
    if meta.get("source_module") == "cc_stream_mux" and trigger == "inp_data_i":
        trigger = "inp_data_i[inp_sel_i]"
    candidates = [
        (
            "single_cycle_implication",
            sampled(clock, reset, f"{trigger} |-> !$isunknown({observed})"),
            True,
            "Only checks a same-sample consequence and omits the required temporal history or exact functional value.",
        ),
        (
            "final_output_only",
            sampled(clock, reset, f"!$isunknown({observed})"),
            False,
            "Observes only whether the selected output is known; it ignores the protocol trigger and correct value.",
        ),
        (
            "delay_removed",
            sampled(clock, reset, f"{trigger} |-> {observed}"),
            True,
            "Checks only an overlapped output polarity, deliberately removing any next-cycle, ranged-delay, or duration requirement.",
        ),
        (
            "antecedent_removed",
            sampled(clock, reset, f"!$isunknown({observed})"),
            False,
            "Drops the behavioral antecedent entirely and retains only a shallow output-integrity check.",
        ),
        (
            "simple_invariant",
            sampled(clock, reset, f"!$isunknown({trigger}) && !$isunknown({observed})"),
            False,
            "A shallow signal-integrity invariant that does not encode ordering, polarity, delay, duration, or the expected output value.",
        ),
    ]
    return [
        {
            "id": f"weak_{i:02d}_{kind}",
            "weakness_class": kind,
            "sva": sva,
            "nonempty_antecedent": nonempty,
            "rationale": rationale,
            "validation_status": "pending_formal_validation",
            "compile_ok": None,
            "nonvacuous": None,
            "misses_bug_primary": None,
            "misses_bug_heldout": None,
        }
        for i, (kind, sva, nonempty, rationale) in enumerate(candidates, 1)
    ]


def main() -> None:
    count = 0
    for case_dir in sorted(ROOT.glob("case*")):
        metadata_path = case_dir / "case_metadata.json"
        if not metadata_path.exists():
            continue
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        if meta.get("source_project") != "common_cells":
            continue
        assertions = build(meta)
        payload = {
            "schema_version": "1.0",
            "case_id": case_dir.name,
            "parent_bug_id": meta.get("parent_bug_id"),
            "source_project": "common_cells",
            "purpose": "task4_hardness_screening_candidates",
            "overall_validation_status": "pending_formal_validation",
            "admission_decision": None,
            "admission_rule": "At least two non-vacuous weak assertions must miss the bug before admission.",
            "assertions": assertions,
        }
        (case_dir / "weak_assertions.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        sva_lines = [
            f"// Weak assertion candidates for {case_dir.name}",
            "// STATUS: PENDING FORMAL VALIDATION; this file makes no admission claim.",
            "",
        ]
        for item in assertions:
            sva_lines += [
                f"// {item['id']} [{item['weakness_class']}]",
                f"// nonempty_antecedent={str(item['nonempty_antecedent']).lower()}",
                item["sva"],
                "",
            ]
        (case_dir / "weak_assertions.sva").write_text("\n".join(sva_lines), encoding="utf-8")
        count += 1
    if count != 19:
        raise SystemExit(f"expected 19 common_cells cases, generated {count}")
    print(f"generated weak assertion assets for {count} common_cells cases")


if __name__ == "__main__":
    main()
