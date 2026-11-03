#!/usr/bin/env python3
import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Sequence, Set

from sva_eval_grammar import extract_single_assertion


IDENT_RE = re.compile(r"\b[A-Za-z_]\w*(?:\[\d+(?::\d+)?\])?\b")
SV_NUMBER_RE = re.compile(r"\b\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ_]+\b")

KEYWORDS = {
    "assert",
    "property",
    "posedge",
    "disable",
    "iff",
    "clk",
    "true",
    "false",
    "and",
    "or",
    "not",
    "past",
}


def signal_base_name(name: str) -> str:
    return re.sub(r"\[.*\]$", "", (name or "").strip())


def collect_signals(expr_text: str) -> List[str]:
    cleaned = SV_NUMBER_RE.sub(" ", expr_text)
    signals: List[str] = []
    seen: Set[str] = set()
    for token in IDENT_RE.findall(cleaned):
        base = signal_base_name(token)
        if base.lower() in KEYWORDS:
            continue
        if base not in seen:
            seen.add(base)
            signals.append(base)
    return signals


def extract_used_signals(assertion_text: str) -> Dict[str, List[str]]:
    _full, disable_expr, ante, _op, cons = extract_single_assertion(assertion_text)
    behavioral_expr = " ".join(part for part in [ante, cons] if part)
    return {
        "behavioral": collect_signals(behavioral_expr),
        "reset_gating": collect_signals(disable_expr or ""),
    }


def load_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def posedge_rows(csv_rows: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    if not csv_rows:
        return []
    rows: List[Dict[str, str]] = []
    prev_clk = csv_rows[0].get("clk", "0")
    for row in csv_rows[1:]:
        curr_clk = row.get("clk", "0")
        if prev_clk == "0" and curr_clk == "1":
            rows.append(row)
        prev_clk = curr_clk
    return rows


def first_divergence_time_ps(case_dir: Path, cycle_index: int) -> str:
    waveform_path = case_dir / "waveform_good.csv"
    if not waveform_path.exists():
        return ""
    rows = posedge_rows(load_csv_rows(waveform_path))
    if cycle_index < 0 or cycle_index >= len(rows):
        return ""
    return rows[cycle_index].get("time_ps", "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit whether golden metadata columns match the actual golden SVA and current trace summaries."
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument(
        "--output-csv",
        default="golden_metadata_audit.csv",
        help="Output CSV path.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest = json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))
    cases = manifest["cases"]

    fields = [
        "case_name",
        "expected_behavior_present",
        "expected_behavior",
        "first_divergence_cycle_manifest",
        "first_divergence_cycle_trace",
        "first_divergence_cycle_match",
        "first_divergence_time_ps_manifest",
        "first_divergence_time_ps_waveform",
        "first_divergence_time_match",
        "relevant_signals_manifest",
        "signals_used_in_sva_behavioral",
        "signals_used_in_disable_iff",
        "relevant_signals_match",
        "missing_from_relevant_signals",
        "extra_in_relevant_signals",
        "temporal_type_present",
        "temporal_type",
        "overall_pass",
    ]

    rows: List[Dict[str, object]] = []
    for case in cases:
        case_name = str(case.get("name", ""))
        case_dir = root / case_name
        golden = case.get("golden_sva", {})
        assertion_text = str(golden.get("sva", "")).strip()
        trace_summary_path = case_dir / "experiment" / "trace_summary.json"
        trace_summary = (
            json.loads(trace_summary_path.read_text(encoding="utf-8"))
            if trace_summary_path.exists()
            else {}
        )

        expected_behavior = str(golden.get("expected_behavior", "")).strip()
        expected_behavior_present = bool(expected_behavior)

        manifest_cycle = golden.get("first_divergence_cycle")
        trace_cycle = trace_summary.get("first_divergence_cycle")
        cycle_match = manifest_cycle == trace_cycle

        manifest_time = str(golden.get("first_divergence_time_ps", ""))
        waveform_time = ""
        if isinstance(trace_cycle, int):
            waveform_time = first_divergence_time_ps(case_dir, trace_cycle)
        time_match = manifest_time == waveform_time

        manifest_signals_raw = [str(item) for item in golden.get("relevant_signals", [])]
        manifest_signals = [signal_base_name(item) for item in manifest_signals_raw]
        used_signal_groups = extract_used_signals(assertion_text)
        used_signals = used_signal_groups["behavioral"]
        reset_signals = used_signal_groups["reset_gating"]
        manifest_set = set(manifest_signals)
        used_set = set(used_signals)
        missing = [sig for sig in used_signals if sig not in manifest_set]
        extra = [sig for sig in manifest_signals if sig not in used_set]
        relevant_match = not missing and not extra

        temporal_type = str(golden.get("temporal_type", "")).strip()
        temporal_type_present = bool(temporal_type)

        overall_pass = (
            expected_behavior_present
            and cycle_match
            and time_match
            and relevant_match
            and temporal_type_present
        )

        rows.append(
            {
                "case_name": case_name,
                "expected_behavior_present": expected_behavior_present,
                "expected_behavior": expected_behavior,
                "first_divergence_cycle_manifest": manifest_cycle,
                "first_divergence_cycle_trace": trace_cycle,
                "first_divergence_cycle_match": cycle_match,
                "first_divergence_time_ps_manifest": manifest_time,
                "first_divergence_time_ps_waveform": waveform_time,
                "first_divergence_time_match": time_match,
                "relevant_signals_manifest": ", ".join(manifest_signals),
                "signals_used_in_sva_behavioral": ", ".join(used_signals),
                "signals_used_in_disable_iff": ", ".join(reset_signals),
                "relevant_signals_match": relevant_match,
                "missing_from_relevant_signals": ", ".join(missing),
                "extra_in_relevant_signals": ", ".join(extra),
                "temporal_type_present": temporal_type_present,
                "temporal_type": temporal_type,
                "overall_pass": overall_pass,
            }
        )

    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    passed = sum(1 for row in rows if row["overall_pass"])
    total = len(rows)
    print(f"[DONE] Wrote audit report: {out_csv}")
    print(f"SUMMARY: {passed}/{total} golden metadata rows pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
