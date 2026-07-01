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


def build_text_summary(
    case_meta: Dict,
    first_cycle: Optional[int],
    differing: Sequence[str],
    snapshot: Sequence[Dict[str, str]],
) -> str:
    lines = [
        f"Case: {case_meta['name']}",
        "First divergence cycle: " + ("none" if first_cycle is None else str(first_cycle)),
        "Differing signals at first divergence: " + (", ".join(differing) if differing else "(none)"),
    ]
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
    if first_cycle is not None and first_cycle < len(good_cycle) and first_cycle < len(bad_cycle):
        snapshot = collect_divergence_snapshot(
            good_cycle[first_cycle],
            bad_cycle[first_cycle],
            differing,
        )

    return {
        "case_name": case_meta["name"],
        "first_divergence_cycle": first_cycle,
        "differing_signals": list(differing),
        "divergence_snapshot": snapshot,
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
        text_summary = build_text_summary(
            case_meta,
            summary["first_divergence_cycle"],
            summary["differing_signals"],
            summary["divergence_snapshot"],
        )
        write_text(exp_dir / "trace_summary.txt", text_summary + "\n")
        write_text(
            exp_dir / "trace_summary.json",
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        )
        print(f"[OK] Summarized trace divergence for {case_meta['name']}")


if __name__ == "__main__":
    main()
