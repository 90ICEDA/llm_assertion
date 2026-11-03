from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd


METHODS = [
    "spec_only",
    "spec_rtl_full",
    "spec_rtl_interface",
    "spec_rtl_signal_list",
    "spec_rtl_sliced",
    "spec_rtl_signal_list_small_slice",
]
MODELS = {"GPT": "gpt-5.4", "Claude": "claude-opus-4-8"}
KEY = ["model_label", "provider", "model_name", "case_id", "method", "candidate_index"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze and report the formal six-context dual-model experiment.")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--small-slice", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260721)
    args = parser.parse_args()

    baseline_path = args.baseline.resolve()
    small_path = args.small_slice.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    baseline = pd.read_csv(baseline_path)
    small = pd.read_csv(small_path)
    def derived_parent(case_id: object) -> str:
        text = str(case_id)
        match = re.search(r"_from_(case\d+_.+)$", text)
        return match.group(1) if match else text
    for frame in (baseline, small):
        derived = frame["case_id"].map(derived_parent)
        if "parent_bug_id" not in frame.columns:
            frame["parent_bug_id"] = derived
        else:
            missing = frame["parent_bug_id"].isna() | frame["parent_bug_id"].astype(str).str.strip().isin({"", "nan", "None"})
            frame.loc[missing, "parent_bug_id"] = derived.loc[missing]
    expected_baseline_methods = set(METHODS[:-1])
    if set(baseline["method"].unique()) != expected_baseline_methods:
        raise RuntimeError("Baseline must contain exactly the five pre-existing RTL-context methods.")
    if set(small["method"].unique()) != {METHODS[-1]}:
        raise RuntimeError("New results must contain only spec_rtl_signal_list_small_slice.")

    frames = []
    for name, frame, method_count in [("baseline", baseline, 5), ("small-slice", small, 1)]:
        if set(frame["model_label"].unique()) != set(MODELS):
            raise RuntimeError(f"{name}: expected exactly GPT and Claude")
        for label, model_name in MODELS.items():
            observed = set(frame.loc[frame["model_label"] == label, "model_name"].astype(str))
            if observed != {model_name}:
                raise RuntimeError(f"{name}: {label} model mismatch: {sorted(observed)}")
        if frame.duplicated(KEY).any():
            raise RuntimeError(f"{name}: duplicate candidate keys")
        frames.append(frame)

    case_ids = set(baseline["case_id"].astype(str))
    if len(case_ids) != 120 or set(small["case_id"].astype(str)) != case_ids:
        raise RuntimeError("Both inputs must cover the same exact 120 cases.")
    expected_baseline = 120 * 2 * 5 * args.k
    expected_small = 120 * 2 * args.k
    if len(baseline) != expected_baseline or len(small) != expected_small:
        raise RuntimeError(
            f"Row-count contract failed: baseline={len(baseline)}/{expected_baseline}, "
            f"small-slice={len(small)}/{expected_small}"
        )
    for frame in frames:
        indices = set(pd.to_numeric(frame["candidate_index"], errors="raise").astype(int))
        if indices != set(range(1, args.k + 1)):
            raise RuntimeError(f"candidate_index contract failed: {sorted(indices)}")

    merged = pd.concat(frames, ignore_index=True).sort_values(KEY).reset_index(drop=True)
    merged_path = out / "multi_model_results_raw.csv"
    merged.to_csv(merged_path, index=False)

    stats_dir = out / "formal_statistics"
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("build_rtl_context_generalization_statistics.py")),
        str(merged_path),
        str(stats_dir),
        "--k", str(args.k),
        "--repetitions", str(args.repetitions),
        "--seed", str(args.seed),
    ]
    subprocess.run(cmd, check=True)

    generated = sorted(path for path in stats_dir.rglob("*") if path.is_file())
    provenance = {
        "schema_version": 1,
        "status": "frozen_formal_six_context_dual_model",
        "models": MODELS,
        "k": args.k,
        "case_count": 120,
        "parent_count": int(merged["parent_bug_id"].nunique()),
        "candidate_count": int(len(merged)),
        "methods": METHODS,
        "overlap_status": "overlap",
        "overlap_definition": "the exact same 40 parent_bug_id values occur in every model/method cell",
        "bootstrap_unit": "parent_bug_id",
        "bootstrap_repetitions": args.repetitions,
        "bootstrap_confidence_level": 0.95,
        "paired_test": "McNemar",
        "effect_size": "paired risk difference",
        "inputs": {
            str(baseline_path): sha256(baseline_path),
            str(small_path): sha256(small_path),
        },
        "outputs": {
            str(merged_path): sha256(merged_path),
            **{str(path): sha256(path) for path in generated},
        },
    }
    freeze_path = out / "formal_experiment_freeze.json"
    freeze_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(provenance, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
