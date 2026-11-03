#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "rtl_cases_real_scale210_independent_next"
FINAL = REPO / "deliverables/final_dataset_acceptance_20260804/final_manifest.json"
RAW_TRACE_MAX_CYCLES = 64


def base(name: str) -> str:
    return re.sub(r"\[[^]]+\]$", "", name)


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def trace_text(path: Path) -> str:
    rows = csv_rows(path)
    columns = [name for name in rows[0] if name != "time_ps"] if rows else []
    clock = next((name for name in ("clk", "clk_i") if name in columns), None)
    selected = []
    if clock:
        previous = "0"
        for row in rows:
            current = row.get(clock, "x")
            if previous == "0" and current == "1":
                selected.append(row)
            previous = current
    else:
        selected = rows
    lines = []
    # Use the same bounded raw-cycle budget for every case and model.  Some
    # testbenches run for hundreds of cycles; emitting all of them can exceed
    # a provider's request limit and would make the method budget unequal.
    selected = selected[:RAW_TRACE_MAX_CYCLES]
    for index, row in enumerate(selected):
        values = ", ".join(f"{name}={row.get(name, '')}" for name in columns)
        lines.append(f"cycle {index}: {values}")
    return "\n".join(lines) + "\n"


def trace_summary(good_path: Path, bad_path: Path, case_name: str) -> tuple[str, dict]:
    good, bad = csv_rows(good_path), csv_rows(bad_path)
    limit = min(len(good), len(bad))
    index = next((i for i in range(limit) if good[i] != bad[i]), -1)
    if index < 0:
        raise RuntimeError(f"no divergence: {case_name}")
    signals = [key for key in good[index] if key != "time_ps" and good[index].get(key) != bad[index].get(key)]
    good_values = ", ".join(f"{key}={good[index].get(key)}" for key in signals)
    bad_values = ", ".join(f"{key}={bad[index].get(key)}" for key in signals)
    text = "\n".join([
        f"Case: {case_name}",
        f"First divergence cycle: {index}",
        f"First divergence time_ps: {good[index].get('time_ps', '')}",
        f"Differing signals at first divergence: {', '.join(signals)}",
        f"Observed differing signal values (good): {good_values}",
        f"Observed differing signal values (bad): {bad_values}",
    ]) + "\n"
    payload = {
        "case_name": case_name,
        "first_divergence_cycle": index,
        "first_divergence_time_ps": good[index].get("time_ps", ""),
        "differing_signals": signals,
        "divergence_snapshot": [
            {"signal": key, "good": good[index].get(key), "bad": bad[index].get(key)} for key in signals
        ],
        "divergence_observation": "sampled_csv_row",
    }
    return text, payload


def prompt(*, spec: str, signals: list[str], rtl: str = "", trace: str = "") -> str:
    clock = "clk" if "clk" in signals else "clk_i" if "clk_i" in signals else signals[0]
    reset = "!rst_n" if "rst_n" in signals else "!rst_ni" if "rst_ni" in signals else "rst" if "rst" in signals else "1'b0"
    sections = [
        "You are a formal verification engineer.",
        f"Generate SystemVerilog assertions using @(posedge {clock}) disable iff ({reset}).",
        "Use only allowed signals. Output assertion lines only.",
        "Allowed signals:", ", ".join(signals),
        "Specification:", spec,
    ]
    if rtl:
        sections += ["RTL:", rtl]
    if trace:
        sections += ["Waveform evidence:", trace]
    return "\n\n".join(sections).strip() + "\n"


def main() -> None:
    final = json.loads(FINAL.read_text(encoding="utf-8"))
    manifest_cases = []
    for item in final["cases"]:
        name = item["name"]
        case_dir = ROOT / name
        meta = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
        experiment = case_dir / "experiment"
        prompts = experiment / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        spec = (case_dir / "spec.md").read_text(encoding="utf-8").strip()
        rtl = (case_dir / "correct.v").read_text(encoding="utf-8").strip()
        header = next(csv.reader((case_dir / "waveform_good.csv").open(encoding="utf-8-sig")))
        visible = {base(value) for value in header if value != "time_ps"}
        signals = [base(value) for value in meta["relevant_signals"] if base(value) in visible]
        signals = list(dict.fromkeys(signals))
        if not signals:
            raise RuntimeError(f"no visible relevant signals: {name}")
        (experiment / "spec.txt").write_text(spec + "\n", encoding="utf-8")
        for label, suffix in (("good", ""), ("bad", ""), ("good_holdout", "_holdout"), ("bad_holdout", "_holdout")):
            kind = "good" if label.startswith("good") else "bad"
            (experiment / f"trace_{label}.txt").write_text(
                trace_text(case_dir / f"waveform_{kind}{suffix}.csv"), encoding="utf-8"
            )
        summary, summary_json = trace_summary(case_dir / "waveform_good.csv", case_dir / "waveform_bad.csv", name)
        (experiment / "trace_summary.txt").write_text(summary, encoding="utf-8")
        (experiment / "trace_summary.json").write_text(json.dumps(summary_json, indent=2) + "\n", encoding="utf-8")
        raw = "Good trace (sampled cycles):\n" + (experiment / "trace_good.txt").read_text(encoding="utf-8")
        raw += "\nBad trace (sampled cycles):\n" + (experiment / "trace_bad.txt").read_text(encoding="utf-8")
        (prompts / "prompt_1_spec_only.txt").write_text(prompt(spec=spec, signals=signals), encoding="utf-8")
        (prompts / "prompt_2_spec_plus_rtl.txt").write_text(prompt(spec=spec, signals=signals, rtl=rtl), encoding="utf-8")
        (prompts / "prompt_3_spec_rtl_raw_trace.txt").write_text(prompt(spec=spec, signals=signals, rtl=rtl, trace=raw), encoding="utf-8")
        (prompts / "prompt_4_spec_rtl_trace_summary.txt").write_text(prompt(spec=spec, signals=signals, rtl=rtl, trace=summary), encoding="utf-8")
        manifest_cases.append({
            "name": name, "parent_bug_id": meta["parent_bug_id"], "bug_class": meta["bug_class"],
            "source_project": meta["source_project"], "bug_family": meta["bug_family"],
            "relevant_signals": signals,
        })
    manifest = {
        "schema_version": 2, "dataset_status": "final46_main_experiment_ready",
        "case_count": len(manifest_cases), "parent_bug_count": len({x["parent_bug_id"] for x in manifest_cases}),
        "cases": manifest_cases,
    }
    (ROOT / "case_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_count": len(manifest_cases), "parent_bug_count": manifest["parent_bug_count"]}, indent=2))


if __name__ == "__main__":
    main()
