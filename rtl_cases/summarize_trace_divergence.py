#!/usr/bin/env python3
import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


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


def resolve_selected_signals(key_signals: Sequence[str], columns: Sequence[str]) -> List[str]:
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


def to_cycle_trace(rows: List[Dict[str, str]], key_signals: Sequence[str]) -> List[Dict[str, str]]:
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

    out: List[Dict[str, str]] = []
    cycle = 0

    if has_clk:
        prev = rows[0].get("clk", "0")
        interval_start = 1
        for i in range(1, len(rows)):
            curr = rows[i].get("clk", "0")
            if is_rising_edge(prev, curr):
                entry = {"cycle": str(cycle), "time_ps": rows[i].get("time_ps", "")}
                for s in selected:
                    value = rows[i].get(s, "")
                    if s.endswith("_pulse_o"):
                        window = rows[interval_start : i + 1]
                        value = "1" if any(r.get(s, "") == "1" for r in window) else "0"
                    entry[s] = value
                out.append(entry)
                cycle += 1
                interval_start = i + 1
            prev = curr
    else:
        for r in rows:
            entry = {"cycle": str(cycle), "time_ps": r.get("time_ps", "")}
            for s in selected:
                entry[s] = r.get(s, "")
            out.append(entry)
            cycle += 1
    return out

def find_first_divergence(
    good_cycle: List[Dict[str, str]], bad_cycle: List[Dict[str, str]]
) -> Tuple[Optional[int], List[str]]:
    if not good_cycle or not bad_cycle:
        return None, []

    shared = [
        col
        for col in good_cycle[0].keys()
        if col != "cycle" and col in bad_cycle[0]
    ]
    count = min(len(good_cycle), len(bad_cycle))
    for idx in range(count):
        diffs = [col for col in shared if good_cycle[idx].get(col, "") != bad_cycle[idx].get(col, "")]
        if diffs:
            return idx, diffs
    return None, []


def find_first_raw_divergence(
    good_rows: List[Dict[str, str]],
    bad_rows: List[Dict[str, str]],
    key_signals: Sequence[str],
) -> Tuple[Optional[int], str, List[str]]:
    if not good_rows or not bad_rows:
        return None, "", []

    shared_cols = [col for col in good_rows[0].keys() if col in bad_rows[0]]
    shared = [
        col
        for col in resolve_selected_signals(key_signals, shared_cols)
        if col not in {"time_ps"}
    ]
    count = min(len(good_rows), len(bad_rows))
    for idx in range(count):
        diffs = [col for col in shared if good_rows[idx].get(col, "") != bad_rows[idx].get(col, "")]
        if diffs:
            return idx, good_rows[idx].get("time_ps", ""), diffs
    return None, "", []


def collect_divergence_snapshot(
    good_row: Dict[str, str],
    bad_row: Dict[str, str],
    differing: Sequence[str],
) -> List[Dict[str, str]]:
    snapshot: List[Dict[str, str]] = []
    for name in differing:
        snapshot.append(
            {
                "signal": name,
                "good": good_row.get(name, ""),
                "bad": bad_row.get(name, ""),
            }
        )
    return snapshot


def format_signal_pairs(snapshot: Sequence[Dict[str, str]], side: str) -> str:
    return ", ".join(f"{item['signal']}={item[side]}" for item in snapshot)


def build_text_summary(case_meta: Dict, summary: Dict[str, object]) -> str:
    first_cycle = summary.get("first_divergence_cycle")
    differing = summary.get("differing_signals") or []
    snapshot = summary.get("divergence_snapshot") or []
    observation = str(summary.get("divergence_observation", "") or "")
    first_time_ps = str(summary.get("first_divergence_time_ps", "") or "")
    lines = [
        f"Case: {case_meta['name']}",
        "First divergence cycle: " + ("none" if first_cycle is None else str(first_cycle)),
        "Differing signals at first divergence: " + (", ".join(differing) if differing else "(none)"),
    ]
    if observation == "raw_timestamp" and first_time_ps:
        lines.append(
            "Observation basis: raw waveform at "
            + first_time_ps
            + " ps (the first differing pulse happens between sampled posedges)"
        )
    if snapshot:
        lines.append("Observed differing signal values (good): " + format_signal_pairs(snapshot, "good"))
        lines.append("Observed differing signal values (bad): " + format_signal_pairs(snapshot, "bad"))
    return "\n".join(lines)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def summarize_case(root: Path, case_meta: Dict) -> Dict[str, object]:
    case_dir = root / case_meta["name"]
    good_rows = read_csv_rows(case_dir / "waveform_good.csv")
    bad_rows = read_csv_rows(case_dir / "waveform_bad.csv")
    good_cycle = to_cycle_trace(good_rows, case_meta["key_signals"])
    bad_cycle = to_cycle_trace(bad_rows, case_meta["key_signals"])

    first_cycle, differing = find_first_divergence(good_cycle, bad_cycle)
    snapshot: List[Dict[str, str]] = []
    first_divergence_cycle: Optional[object] = first_cycle
    first_divergence_time_ps = ""
    divergence_observation = ""

    if first_cycle is not None and first_cycle < len(good_cycle) and first_cycle < len(bad_cycle):
        snapshot = collect_divergence_snapshot(
            good_cycle[first_cycle],
            bad_cycle[first_cycle],
            differing,
        )
        first_divergence_time_ps = good_cycle[first_cycle].get("time_ps", "")
        divergence_observation = "posedge_cycle"
    else:
        raw_idx, raw_time_ps, raw_differing = find_first_raw_divergence(
            good_rows,
            bad_rows,
            case_meta["key_signals"],
        )
        if raw_idx is not None and raw_idx < len(good_rows) and raw_idx < len(bad_rows):
            first_divergence_cycle = f"raw@{raw_time_ps}ps"
            first_divergence_time_ps = raw_time_ps
            divergence_observation = "raw_timestamp"
            differing = raw_differing
            snapshot = collect_divergence_snapshot(
                good_rows[raw_idx],
                bad_rows[raw_idx],
                differing,
            )

    return {
        "case_name": case_meta["name"],
        "first_divergence_cycle": first_divergence_cycle,
        "first_divergence_time_ps": first_divergence_time_ps,
        "differing_signals": list(differing),
        "divergence_snapshot": snapshot,
        "divergence_observation": divergence_observation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize first divergence between good/bad traces for rtl_cases."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Path to rtl_cases root directory (default: current directory).",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cases = read_manifest(root)

    for case_meta in cases:
        summary = summarize_case(root, case_meta)
        case_dir = root / case_meta["name"]
        exp_dir = case_dir / "experiment"
        text_summary = build_text_summary(case_meta, summary)
        write_text(exp_dir / "trace_summary.txt", text_summary + "\n")
        write_text(
            exp_dir / "trace_summary.json",
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        )
        print(f"[OK] Summarized trace divergence for {case_meta['name']}")


if __name__ == "__main__":
    main()
