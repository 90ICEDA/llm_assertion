#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


def read_manifest(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def signal_base_name(name: str) -> str:
    if "[" in name:
        return name.split("[", 1)[0]
    return name


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
    selected = resolve_selected_signals(key_signals, keys)
    if "clk" in keys and "clk" not in selected:
        selected = ["clk"] + selected
    if "rst_n" in keys and "rst_n" not in selected:
        selected = ["rst_n"] + selected

    out: List[Dict[str, str]] = []
    prev_clk = rows[0].get("clk", "0")
    cycle = 0
    interval_start = 1
    for row_idx, row in enumerate(rows[1:], start=1):
        curr_clk = row.get("clk", "0")
        if prev_clk == "0" and curr_clk == "1":
            entry = {"cycle": str(cycle), "time_ps": row.get("time_ps", "")}
            for sig in selected:
                value = row.get(sig, "")
                if sig.endswith("_pulse_o"):
                    window = rows[interval_start : row_idx + 1]
                    value = "1" if any(r.get(sig, "") == "1" for r in window) else "0"
                entry[sig] = value
            out.append(entry)
            cycle += 1
            interval_start = row_idx + 1
        prev_clk = curr_clk
    return out


def first_divergence(
    good_rows: List[Dict[str, str]],
    bad_rows: List[Dict[str, str]],
) -> Tuple[Optional[int], str, List[str]]:
    if not good_rows or not bad_rows:
        return None, "", []

    shared = [col for col in good_rows[0].keys() if col in bad_rows[0] and col not in {"cycle", "time_ps"}]
    count = min(len(good_rows), len(bad_rows))
    for idx in range(count):
        diffs = [col for col in shared if good_rows[idx].get(col, "") != bad_rows[idx].get(col, "")]
        if diffs:
            return idx, good_rows[idx].get("time_ps", ""), diffs
    return None, "", []


def first_raw_divergence(
    good_rows: List[Dict[str, str]],
    bad_rows: List[Dict[str, str]],
    key_signals: Sequence[str],
) -> Tuple[Optional[str], str, List[str]]:
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
            time_ps = good_rows[idx].get("time_ps", "")
            return f"raw@{time_ps}ps", time_ps, diffs
    return None, "", []


def check_pair(case_dir: Path, key_signals: Sequence[str], good_name: str, bad_name: str) -> Dict[str, object]:
    good_path = case_dir / good_name
    bad_path = case_dir / bad_name
    if not good_path.exists() or not bad_path.exists():
        return {
            "files_present": False,
            "diverges": False,
            "first_divergence_cycle": "",
            "first_divergence_time_ps": "",
            "differing_signals": "",
        }

    good_cycle = to_cycle_trace(read_csv_rows(good_path), key_signals)
    bad_cycle = to_cycle_trace(read_csv_rows(bad_path), key_signals)
    cycle, time_ps, differing = first_divergence(good_cycle, bad_cycle)
    observation = "posedge_cycle" if cycle is not None else ""
    first_cycle_value: object = "" if cycle is None else cycle
    if cycle is None:
        raw_cycle, raw_time_ps, raw_differing = first_raw_divergence(
            read_csv_rows(good_path),
            read_csv_rows(bad_path),
            key_signals,
        )
        if raw_cycle is not None:
            cycle = raw_cycle
            first_cycle_value = raw_cycle
            time_ps = raw_time_ps
            differing = raw_differing
            observation = "raw_timestamp"
    return {
        "files_present": True,
        "diverges": cycle is not None,
        "first_divergence_cycle": first_cycle_value,
        "first_divergence_time_ps": time_ps,
        "differing_signals": ", ".join(differing),
        "first_divergence_observation": observation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit whether seen, held-out, and decoy good/bad traces actually diverge on sampled cycles."
    )
    parser.add_argument("--root", required=True, help="Dataset root containing case_manifest.json.")
    parser.add_argument(
        "--output-csv",
        default="trace_divergence_gate_report.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional case name filter. Repeat to evaluate multiple cases.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest = read_manifest(root)
    requested = {name.strip() for name in args.case if name.strip()}
    if requested:
        unknown = sorted(requested - {str(case["name"]) for case in manifest})
        if unknown:
            raise RuntimeError(f"Unknown case filters: {', '.join(unknown)}")
        selected_cases = [case for case in manifest if str(case["name"]) in requested]
    else:
        selected_cases = manifest
    rows: List[Dict[str, object]] = []
    for case in selected_cases:
        case_name = str(case["name"])
        key_signals = [str(sig) for sig in case.get("key_signals", [])]
        case_dir = root / case_name
        primary = check_pair(case_dir, key_signals, "waveform_good.csv", "waveform_bad.csv")
        heldout = check_pair(case_dir, key_signals, "waveform_good_holdout.csv", "waveform_bad_holdout.csv")
        decoy = check_pair(case_dir, key_signals, "waveform_good_decoy.csv", "waveform_bad_decoy.csv")
        rows.append(
            {
                "case_name": case_name,
                "bug_class": str(case.get("bug_class", "")),
                "primary_files_present": primary["files_present"],
                "primary_diverges": primary["diverges"],
                "primary_first_divergence_cycle": primary["first_divergence_cycle"],
                "primary_first_divergence_time_ps": primary["first_divergence_time_ps"],
                "primary_differing_signals": primary["differing_signals"],
                "primary_first_divergence_observation": primary["first_divergence_observation"],
                "heldout_files_present": heldout["files_present"],
                "heldout_diverges": heldout["diverges"],
                "heldout_first_divergence_cycle": heldout["first_divergence_cycle"],
                "heldout_first_divergence_time_ps": heldout["first_divergence_time_ps"],
                "heldout_differing_signals": heldout["differing_signals"],
                "heldout_first_divergence_observation": heldout["first_divergence_observation"],
                "decoy_files_present": decoy["files_present"],
                "decoy_diverges": decoy["diverges"],
                "decoy_first_divergence_cycle": decoy["first_divergence_cycle"],
                "decoy_first_divergence_time_ps": decoy["first_divergence_time_ps"],
                "decoy_differing_signals": decoy["differing_signals"],
                "decoy_first_divergence_observation": decoy["first_divergence_observation"],
                "divergence_gate_ok": bool(primary["diverges"]) and bool(heldout["diverges"]) and bool(decoy["diverges"]),
            }
        )

    fields = [
        "case_name",
        "bug_class",
        "primary_files_present",
        "primary_diverges",
        "primary_first_divergence_cycle",
        "primary_first_divergence_time_ps",
        "primary_differing_signals",
        "primary_first_divergence_observation",
        "heldout_files_present",
        "heldout_diverges",
        "heldout_first_divergence_cycle",
        "heldout_first_divergence_time_ps",
        "heldout_differing_signals",
        "heldout_first_divergence_observation",
        "decoy_files_present",
        "decoy_diverges",
        "decoy_first_divergence_cycle",
        "decoy_first_divergence_time_ps",
        "decoy_differing_signals",
        "decoy_first_divergence_observation",
        "divergence_gate_ok",
    ]
    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    passed = sum(1 for row in rows if row["divergence_gate_ok"])
    total = len(rows)
    print(f"[DONE] Wrote divergence gate report: {out_csv}")
    print(f"SUMMARY: {passed}/{total} cases have seen, held-out, and decoy divergence.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
