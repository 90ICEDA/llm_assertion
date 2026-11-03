#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


VARIANTS = (("primary", ""), ("heldout", "_holdout"), ("decoy", "_decoy"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_waveform(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "time_ps" not in reader.fieldnames:
            raise ValueError(f"{path}: missing time_ps column")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: empty waveform")
    previous = -1
    for row in rows:
        current = int(row["time_ps"])
        if current < previous:
            raise ValueError(f"{path}: time_ps is not monotonic")
        previous = current
    return list(reader.fieldnames), rows


def first_divergence(good_path: Path, bad_path: Path) -> dict[str, object]:
    good_columns, good_rows = read_waveform(good_path)
    bad_columns, bad_rows = read_waveform(bad_path)
    signals = sorted((set(good_columns) & set(bad_columns)) - {"time_ps"})
    if not signals:
        raise ValueError(f"{good_path.parent.name}: waveforms have no common signals")

    times = sorted(
        {int(row["time_ps"]) for row in good_rows}
        | {int(row["time_ps"]) for row in bad_rows}
    )
    gi = bi = -1
    good_state: dict[str, str] | None = None
    bad_state: dict[str, str] | None = None
    for sample_index, time_ps in enumerate(times):
        while gi + 1 < len(good_rows) and int(good_rows[gi + 1]["time_ps"]) <= time_ps:
            gi += 1
            good_state = good_rows[gi]
        while bi + 1 < len(bad_rows) and int(bad_rows[bi + 1]["time_ps"]) <= time_ps:
            bi += 1
            bad_state = bad_rows[bi]
        if good_state is None or bad_state is None:
            continue
        differing = [signal for signal in signals if good_state[signal] != bad_state[signal]]
        if differing:
            return {
                "time_ps": time_ps,
                "sample_index": sample_index,
                "good_row_index": gi,
                "bad_row_index": bi,
                "signals": differing,
                "good_values": {signal: good_state[signal] for signal in differing},
                "bad_values": {signal: bad_state[signal] for signal in differing},
            }
    raise ValueError(f"{good_path.parent.name}: no good/bad divergence")


def base_signal(name: str) -> str:
    name = name.split(".")[-1]
    return re.sub(r"\[[^]]+\]$", "", name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute and backfill first divergence for formally admitted cases."
    )
    parser.add_argument(
        "--root", type=Path, default=Path("rtl_cases_real_scale210_independent_next")
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("outputs/scale210_next_first_divergence_backfill"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    admitted_path = root / "hardness_decisions" / "admitted_cases.json"
    admitted = json.loads(admitted_path.read_text(encoding="utf-8"))
    if len(admitted) != 50 or len(set(admitted)) != 50:
        raise SystemExit(f"expected 50 unique admitted cases, found {len(admitted)}")

    report_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    pending_updates: list[tuple[Path, dict[str, object]]] = []
    for case_name in admitted:
        case_dir = root / case_name
        metadata_path = case_dir / "case_metadata.json"
        metadata_before = metadata_path.read_bytes()
        metadata = json.loads(metadata_before.decode("utf-8"))
        relevant = {base_signal(str(signal)) for signal in metadata.get("relevant_signals", [])}
        computed: dict[str, object] = {}
        case_errors: list[str] = []
        for variant, suffix in VARIANTS:
            good = case_dir / f"waveform_good{suffix}.csv"
            bad = case_dir / f"waveform_bad{suffix}.csv"
            try:
                result = first_divergence(good, bad)
                divergent_bases = {base_signal(signal) for signal in result["signals"]}
                if not (divergent_bases & relevant):
                    case_errors.append(
                        f"{variant}: first differing signals do not intersect relevant_signals"
                    )
                result["good_trace_sha256"] = sha256(good)
                result["bad_trace_sha256"] = sha256(bad)
                computed[variant] = result
                report_rows.append({
                    "case_name": case_name,
                    "parent_bug_id": metadata.get("parent_bug_id"),
                    "variant": variant,
                    "time_ps": result["time_ps"],
                    "sample_index": result["sample_index"],
                    "good_row_index": result["good_row_index"],
                    "bad_row_index": result["bad_row_index"],
                    "differing_signal_count": len(result["signals"]),
                    "signals": ";".join(result["signals"]),
                    "relevant_signal_intersection": ";".join(sorted(divergent_bases & relevant)),
                    "good_trace_sha256": result["good_trace_sha256"],
                    "bad_trace_sha256": result["bad_trace_sha256"],
                })
            except (OSError, ValueError) as exc:
                case_errors.append(f"{variant}: {exc}")
        if case_errors:
            failures.append({"case_name": case_name, "errors": case_errors})
        else:
            metadata["first_divergence"] = computed
            pending_updates.append((metadata_path, metadata))

    if failures:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "failures.json").write_text(
            json.dumps(failures, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        raise SystemExit(f"refusing partial update: {len(failures)} cases failed validation")

    if not args.dry_run:
        for metadata_path, metadata in pending_updates:
            metadata_path.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    metadata_hash_lines = [
        f"{case_name}\t{sha256(root / case_name / 'case_metadata.json')}"
        for case_name in admitted
    ]
    admitted_metadata_aggregate_sha256 = hashlib.sha256(
        ("\n".join(metadata_hash_lines) + "\n").encode("utf-8")
    ).hexdigest()

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "first_divergence_audit.csv"
    with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report_rows[0]))
        writer.writeheader()
        writer.writerows(report_rows)
    summary = {
        "schema_version": 1,
        "mode": "dry_run" if args.dry_run else "written",
        "admitted_case_count": len(admitted),
        "variant_count": len(report_rows),
        "expected_variant_count": len(admitted) * len(VARIANTS),
        "complete_case_count": len(pending_updates),
        "failure_case_count": 0,
        "all_complete": len(pending_updates) == len(admitted) and len(report_rows) == 150,
        "alignment": "union of time_ps with forward-held full waveform state",
        "admitted_cases_sha256": sha256(admitted_path),
        "admitted_metadata_aggregate_sha256": admitted_metadata_aggregate_sha256,
        "audit_csv_sha256": sha256(report_path),
    }
    (output_dir / "first_divergence_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
