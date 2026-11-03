from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def signal_base(name: str) -> str:
    return re.sub(r"\[[^]]+\]$", "", name.strip())


def parse_trace(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"cycle\s+(\d+):\s*(.*)", raw.strip(), re.I)
        if not match:
            continue
        row = {"cycle": match.group(1)}
        for piece in match.group(2).split(","):
            if "=" not in piece:
                continue
            key, value = piece.strip().split("=", 1)
            row[signal_base(key)] = value.strip()
        rows.append(row)
    return rows


def changed_signals(previous: dict[str, str], current: dict[str, str]) -> list[str]:
    return sorted(
        key for key in set(previous) | set(current)
        if key != "cycle" and previous.get(key) != current.get(key)
    )


def is_input_like(name: str) -> bool:
    low = name.lower()
    return low.endswith("_i") or low in {"rst_n", "reset_n", "reset", "rst", "clk", "clock"}


def transition_phrase(name: str, before: str, after: str) -> str:
    if before == "0" and after == "1":
        return f"{name} has an observed rising transition"
    if before == "1" and after == "0":
        return f"{name} has an observed falling transition"
    if re.fullmatch(r"[01]+", after or ""):
        ones = after.count("1")
        state = "all-zero" if ones == 0 else "onehot" if ones == 1 else "multihot"
        return f"{name} changes to an observed {state} state"
    return f"{name} has an observed value change"


def run_length(rows: list[dict[str, str]], start: int, signal: str) -> int:
    if start >= len(rows) or signal not in rows[start]:
        return 0
    value = rows[start][signal]
    length = 0
    for row in rows[start:]:
        if row.get(signal) != value:
            break
        length += 1
    return length


def build_summary(case_id: str, spec: str, good: list[dict[str, str]], bad: list[dict[str, str]]) -> tuple[str, dict[str, Any]]:
    limit = min(len(good), len(bad))
    divergence_index = next(
        (i for i in range(limit) if any(good[i].get(k) != bad[i].get(k) for k in set(good[i]) | set(bad[i]) if k != "cycle")),
        None,
    )
    if divergence_index is None:
        raise RuntimeError(f"No good/bad divergence in {case_id}")
    differing = sorted(
        key for key in set(good[divergence_index]) | set(bad[divergence_index])
        if key != "cycle" and good[divergence_index].get(key) != bad[divergence_index].get(key)
    )
    spec_tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_$]*\b", spec))
    trigger_index, trigger_signals = None, []
    for index in range(divergence_index, 0, -1):
        changed = changed_signals(good[index - 1], good[index])
        preferred = [name for name in changed if is_input_like(name) and name in spec_tokens and not name.lower().startswith(("rst", "reset"))]
        fallback = [name for name in changed if is_input_like(name) and not name.lower().startswith(("rst", "reset", "clk"))]
        selected = preferred or fallback
        if selected:
            trigger_index, trigger_signals = index, selected[:3]
            break
    if trigger_index is None:
        trigger_index = divergence_index
        trigger_signals = [name for name in good[trigger_index] if is_input_like(name) and not name.lower().startswith(("rst", "reset", "clk"))][:3]
    if not trigger_signals:
        trigger_signals = differing[:1]

    trigger_bits = [transition_phrase(name, good[max(0, trigger_index - 1)].get(name, "?"), good[trigger_index].get(name, "?")) for name in trigger_signals]
    context_signals = [
        name for name, value in good[divergence_index].items()
        if name not in trigger_signals and name in spec_tokens and is_input_like(name)
        and not name.lower().startswith(("rst", "reset", "clk")) and value in {"0", "1"}
    ][:2]
    trigger_bits.extend(
        f"{name} is observed {'asserted' if good[divergence_index][name] == '1' else 'deasserted'}"
        for name in context_signals
    )
    delay = divergence_index - trigger_index
    polarity_bits = []
    for name in trigger_signals:
        before, after = good[max(0, trigger_index - 1)].get(name, "?"), good[trigger_index].get(name, "?")
        polarity_bits.append(transition_phrase(name, before, after).replace(" has an observed ", " "))
    polarity_bits.extend(
        f"{name} is {'high' if good[divergence_index][name] == '1' else 'low'} in the observed trigger context"
        for name in context_signals
    )
    for name in differing:
        polarity_bits.append(f"at divergence {name} is observed as good={good[divergence_index].get(name, '?')} and bad={bad[divergence_index].get(name, '?')}")

    durations = [run_length(good, trigger_index, name) for name in trigger_signals]
    duration_text = ", ".join(f"{name} holds its observed post-trigger state for {length} sampled cycles" for name, length in zip(trigger_signals, durations))
    resets = [name for name in good[0] if name.lower().startswith(("rst", "reset"))]
    if resets:
        reset = resets[0]
        active = "active-low" if reset.lower().endswith("_n") else "active-high"
        reset_text = f"{reset} is {active} and is observed deasserted before the trigger"
    else:
        reset_text = "reset polarity or reset activity is not observable in the supplied trace"
    divergence_cycle = good[divergence_index].get("cycle", str(divergence_index))
    divergence_text = "; ".join(f"{name}: good={good[divergence_index].get(name, '?')}, bad={bad[divergence_index].get(name, '?')}" for name in differing)
    summary = "\n".join([
        "Temporal-relation abstraction:",
        f"- Trigger: {'; '.join(trigger_bits)} in the seen trace.",
        f"- Polarity: {'; '.join(polarity_bits)}.",
        f"- Ordering: the observed trigger {'coincides with' if delay == 0 else 'precedes'} the first good/bad divergence.",
        f"- Observed delay: the seen trace has an observed delay of exactly {delay} sampled cycles from the selected trigger to first divergence.",
        f"- Duration: {duration_text or 'trigger duration is not identifiable from the supplied trace'}.",
        f"- Reset: {reset_text}.",
        f"- Good/bad divergence: at observed cycle {divergence_cycle}, {divergence_text}.",
        "- Generalization boundary: do not infer a universal property from absolute cycle indices or one-off literal constants; preserve only the observed polarity, ordering, delay, duration, reset context, and good/bad relation.",
    ])
    provenance = {
        "case_id": case_id, "source_inputs": ["experiment/spec.txt", "experiment/trace_good.txt", "experiment/trace_bad.txt"],
        "uses_golden_sva": False, "uses_expected_behavior": False, "uses_buggy_rtl": False,
        "uses_mutation_diff": False, "uses_heldout_trace": False, "uses_decoy_trace": False,
        "trigger_signals": trigger_signals, "observed_delay": delay, "first_divergence_cycle": int(divergence_cycle),
        "differing_signals": differing,
    }
    return summary, provenance


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate contract-v1 temporal abstractions from spec and primary seen traces only.")
    parser.add_argument("--root", default=str(ROOT / "rtl_cases_real_scale120"))
    parser.add_argument("--output", default=str(ROOT / "outputs/formal_temporal_abstractions/temporal_abstractions.json"))
    args = parser.parse_args()
    cases_root, output = Path(args.root).resolve(), Path(args.output).resolve()
    rows = []
    for case_dir in sorted((x for x in cases_root.iterdir() if x.is_dir() and x.name.startswith("case")), key=lambda x: x.name):
        experiment = case_dir / "experiment"
        if not (experiment / "spec.txt").exists():
            continue
        spec = (experiment / "spec.txt").read_text(encoding="utf-8").strip()
        summary, provenance = build_summary(case_dir.name, spec, parse_trace(experiment / "trace_good.txt"), parse_trace(experiment / "trace_bad.txt"))
        rows.append({"case_id": case_dir.name, "abstracted_summary": summary, "source": "deterministic_seen_trace_contract_v1", "provenance": provenance})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"generated {len(rows)} abstractions -> {output}")


if __name__ == "__main__":
    main()
