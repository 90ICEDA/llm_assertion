from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from unified_result_reporting import normalize_raw_results


METHODS = {
    "spec_rtl_raw_trace",
    "spec_rtl_naive_summary",
    "spec_rtl_event_abstraction",
    "spec_rtl_temporal_relation_abstraction",
}
MODELS = {"GPT": "gpt-5.4", "Claude": "claude-opus-4-8"}
KEY = ["model_label", "provider", "model_name", "case_id", "method", "candidate_index"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate and freeze formal four-trace reports with verified overlap.")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--contract-audit", type=Path, default=None)
    parser.add_argument("--representation-artifact", type=Path, default=None)
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    raw_path = data_dir / "multi_model_results_raw.csv"
    unified_path = data_dir / "unified_three_scope_report.csv"
    stats_dir = data_dir / "parent_statistics"
    ci_path = stats_dir / "method_results_with_parent_bootstrap_ci.csv"
    paired_path = stats_dir / "paired_mcnemar_effect_sizes.csv"
    freeze_path = data_dir / "formal_trace_representation_report_freeze.json"

    original = pd.read_csv(raw_path, encoding="utf-8-sig")
    prompt_path = data_dir / "multi_model_prompt_log.csv"
    prompts = pd.read_csv(prompt_path, encoding="utf-8-sig")
    if len(original) != 1920:
        raise RuntimeError(f"Expected 1920 candidate rows, found {len(original)}")
    if original.duplicated(KEY).any():
        raise RuntimeError("Duplicate candidate keys found")
    if set(original["method"].astype(str)) != METHODS:
        raise RuntimeError(f"Method contract failed: {sorted(set(original['method'].astype(str)))}")
    if set(original["model_label"].astype(str)) != set(MODELS):
        raise RuntimeError("Expected exactly GPT and Claude")
    for label, expected_name in MODELS.items():
        names = set(original.loc[original["model_label"] == label, "model_name"].astype(str))
        if names != {expected_name}:
            raise RuntimeError(f"{label} model mismatch: {sorted(names)}")
    if original["case_id"].nunique() != 120:
        raise RuntimeError(f"Expected 120 cases, found {original['case_id'].nunique()}")
    indices = set(pd.to_numeric(original["candidate_index"], errors="raise").astype(int))
    if indices != set(range(1, args.k + 1)):
        raise RuntimeError(f"Candidate index contract failed: {sorted(indices)}")
    if len(prompts) != 960 or prompts.duplicated(["model_label", "provider", "model_name", "case_id", "method"]).any():
        raise RuntimeError(f"Prompt provenance contract failed: rows={len(prompts)}")
    temporal_prompts = prompts[prompts["method"] == "spec_rtl_temporal_relation_abstraction"]
    if set(temporal_prompts["temporal_contract_status"].astype(str)) != {"formal_compliant"}:
        raise RuntimeError("Temporal prompt provenance is not uniformly formal_compliant")

    normalized = normalize_raw_results(original)
    parent_sets: dict[str, list[str]] = {}
    for (model, method), group in normalized.groupby(["model", "method"], sort=True):
        key = f"{model}/{method}"
        parent_sets[key] = sorted(set(group["parent_bug_id"].astype(str)))
    reference = next(iter(parent_sets.values()))
    if len(reference) != 40:
        raise RuntimeError(f"Expected 40 independent parents, found {len(reference)}")
    mismatched = [key for key, values in parent_sets.items() if values != reference]
    if mismatched:
        raise RuntimeError(f"Parent overlap contract failed for: {mismatched}")

    sample_definition = "scale120; fixed four trace representations; held-out strict success; exact shared 40-parent population"
    common = ["--k", str(args.k), "--metric", "strict_success", "--overlap-status", "overlap", "--sample-definition", sample_definition]
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("unified_result_reporting.py")), str(raw_path), str(unified_path), *common],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("parent_cluster_statistics.py")),
            str(raw_path),
            str(stats_dir),
            *common,
            "--repetitions", str(args.repetitions),
            "--seed", str(args.seed),
            "--parent-outcome", "all_observations",
        ],
        check=True,
    )

    unified = pd.read_csv(unified_path, encoding="utf-8-sig")
    ci = pd.read_csv(ci_path, encoding="utf-8-sig")
    paired = pd.read_csv(paired_path, encoding="utf-8-sig")
    if len(unified) != 72 or len(ci) != 72 or len(paired) != 36:
        raise RuntimeError(f"Report row contract failed: unified={len(unified)}, ci={len(ci)}, paired={len(paired)}")
    if set(unified["overlap_status"].astype(str)) != {"overlap"} or set(ci["overlap_status"].astype(str)) != {"overlap"}:
        raise RuntimeError("Corrected reports do not uniformly declare overlap")
    if ci[["ci_lower", "ci_upper"]].isna().any().any() or paired["mcnemar_p_value"].isna().any():
        raise RuntimeError("Statistical outputs contain missing confidence intervals or p-values")

    abstraction_audit = args.contract_audit.resolve() if args.contract_audit else data_dir.parent / "formal_temporal_abstractions" / "audit" / "trace_representation_contract_audit_summary.json"
    if not abstraction_audit.exists():
        raise RuntimeError(f"Missing contract audit: {abstraction_audit}")
    audit_payload = json.loads(abstraction_audit.read_text(encoding="utf-8"))
    if not audit_payload.get("all_pass") or int(audit_payload.get("pass_cases", 0)) != 120:
        raise RuntimeError("Four-representation contract audit is not 120/120 pass")
    representation_artifact = args.representation_artifact.resolve() if args.representation_artifact else abstraction_audit.with_name("trace_representations.json")
    if not representation_artifact.exists():
        raise RuntimeError(f"Missing fixed representation artifact: {representation_artifact}")
    reuse_provenance = data_dir / "arm_reuse_provenance.json"
    if not reuse_provenance.exists():
        raise RuntimeError("Missing exact-arm reuse provenance")
    reuse_payload = json.loads(reuse_provenance.read_text(encoding="utf-8"))
    if int(reuse_payload.get("remaining_cells", -1)) != 0:
        raise RuntimeError("Arm reuse provenance does not account for all 960 cells")
    freeze = {
        "schema_version": 1,
        "status": "frozen_formal_four_trace_representation_reports",
        "models": MODELS,
        "k": args.k,
        "candidate_count": len(original),
        "case_count": 120,
        "parent_bug_count": 40,
        "methods": sorted(METHODS),
        "selection_scopes": ["candidate_level", "first_candidate", "case_any_of_k"],
        "aggregation_units": ["candidate", "case", "parent_bug"],
        "overlap_status": "overlap",
        "overlap_definition": "all eight model-by-method cells contain the exact same 40 parent_bug_id values",
        "parent_bug_id_backfill": "missing raw values derived from case_id suffix after _from_; base cases map to themselves",
        "bootstrap_unit": "parent_bug_id",
        "bootstrap_repetitions": args.repetitions,
        "bootstrap_confidence_level": 0.95,
        "paired_test": "exact two-sided McNemar",
        "effect_sizes": ["paired risk difference", "matched odds ratio with Haldane correction"],
        "parent_outcome_rule": "all_observations",
        "execution_provenance": "exact representation-identity reuse plus newly generated cells; no outcome-based selection",
        "input_sha256": {
            str(raw_path): sha256(raw_path), str(prompt_path): sha256(prompt_path),
            str(representation_artifact): sha256(representation_artifact), str(reuse_provenance): sha256(reuse_provenance),
        },
        "contract_audit_sha256": sha256(abstraction_audit) if abstraction_audit.exists() else None,
        "output_sha256": {
            str(unified_path): sha256(unified_path),
            str(ci_path): sha256(ci_path),
            str(paired_path): sha256(paired_path),
        },
        "row_counts": {"unified_three_scope": len(unified), "confidence_intervals": len(ci), "paired_comparisons": len(paired)},
        "parent_sets_sha256": hashlib.sha256(json.dumps(parent_sets, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    freeze_path.write_text(json.dumps(freeze, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(freeze, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
