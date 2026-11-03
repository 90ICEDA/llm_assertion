#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "pristine_trace_router_v1"
GENERATED = OUT / "dispatch" / "generated"
FREEZE = OUT / "frozen_test_v1"
K = 2
BOOTSTRAPS = 10_000
SEED = 20260720

SOURCES = {
    "sealed_test_manifest.json": OUT / "sealed_test_manifest.json",
    "locked_policy_multimodel.json": ROOT / "outputs" / "formal_multimodel" / "locked_policy_multimodel.json",
    "test_routing.csv": OUT / "test_routing.csv",
    "trace_representations.json": OUT / "trace_representations.json",
    "dispatcher_temporal_primary.json": OUT / "dispatcher_temporal_primary.json",
    "generation_dispatch_plan.csv": OUT / "dispatch" / "generation_dispatch_plan.csv",
    "multi_model_run_meta.json": GENERATED / "multi_model_run_meta.json",
    "pending_candidates.csv": GENERATED / "pending_candidates.csv",
    "multi_model_results_raw.csv": GENERATED / "multi_model_results_raw.csv",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def percentile(values: list[float], q: float) -> float:
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def copy_immutable(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(src)
    if dst.exists():
        if sha256(src) != sha256(dst):
            raise RuntimeError(f"Refusing to overwrite changed frozen artifact: {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def selected_scores(rows: list[dict[str, str]], scope: str) -> dict[str, list[int]]:
    by_parent: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_parent[row["parent_bug_id"]].append(row)
    result = {}
    for parent, group in by_parent.items():
        ordered = sorted(group, key=lambda r: int(r["candidate_index"]))
        if scope == "candidate_level":
            result[parent] = [int(r["success"]) for r in ordered[:K]]
        elif scope == "first_candidate":
            result[parent] = [int(ordered[0]["success"])]
        elif scope == "case_any_of_k":
            result[parent] = [int(any(int(r["success"]) for r in ordered[:K]))]
        else:
            raise ValueError(scope)
    return result


def metric(scores: dict[str, list[int]], unit: str) -> float:
    if unit == "candidate":
        vals = [x for xs in scores.values() for x in xs]
        return sum(vals) / len(vals)
    # The sealed set has exactly one case per independent parent. Keep both
    # rows to make the reporting contract explicit; their values coincide.
    vals = [sum(xs) / len(xs) for xs in scores.values()]
    return sum(vals) / len(vals)


def bootstrap_ci(scores: dict[str, list[int]], unit: str) -> tuple[float, float]:
    parents = sorted(scores)
    rng = random.Random(SEED)
    reps = []
    for _ in range(BOOTSTRAPS):
        sampled = [parents[rng.randrange(len(parents))] for _ in parents]
        sampled_scores = {f"{i}:{p}": scores[p] for i, p in enumerate(sampled)}
        reps.append(metric(sampled_scores, unit))
    return percentile(reps, 0.025), percentile(reps, 0.975)


def main() -> None:
    FREEZE.mkdir(parents=True, exist_ok=True)
    snapshot = FREEZE / "snapshot"
    for name, src in SOURCES.items():
        copy_immutable(src, snapshot / name)

    existing_manifest_path = FREEZE / "freeze_manifest.json"
    if existing_manifest_path.exists():
        existing = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        for name, expected in existing["source_hashes"].items():
            actual = sha256(snapshot / name)
            if actual != expected:
                raise RuntimeError(f"Frozen source hash mismatch: {name}: {actual} != {expected}")
        for name, expected in existing["report_hashes"].items():
            actual = sha256(FREEZE / name)
            if actual != expected:
                raise RuntimeError(f"Frozen report hash mismatch: {name}: {actual} != {expected}")
        print(json.dumps({
            "frozen": True, "verified_existing_freeze": True,
            "raw_results_sha256": existing["source_hashes"]["multi_model_results_raw.csv"],
            "report_sha256": existing["report_hashes"]["formal_three_scope_report.csv"],
            "manifest_sha256": existing["manifest_sha256"], "output": str(FREEZE),
        }, indent=2, ensure_ascii=False))
        return

    policy = json.loads((snapshot / "locked_policy_multimodel.json").read_text(encoding="utf-8"))
    seal = json.loads((snapshot / "sealed_test_manifest.json").read_text(encoding="utf-8"))
    if not policy.get("locked") or policy.get("fit_scope") != "dev_parent_only":
        raise RuntimeError("Policy is not a dev-parent-only locked policy")
    if not seal.get("sealed") or seal.get("parent_overlap") is not False:
        raise RuntimeError("Pristine test seal is invalid")

    with (snapshot / "multi_model_results_raw.csv").open(encoding="utf-8-sig", newline="") as f:
        raw = list(csv.DictReader(f))
    parents = {c["parent_bug_id"] for c in seal["cases"]}
    if len(raw) != 64:
        raise RuntimeError(f"Expected 64 candidates, found {len(raw)}")
    normalized = []
    for row in raw:
        if row["case_id"] not in parents:
            raise RuntimeError(f"Unsealed case in results: {row['case_id']}")
        normalized.append({
            **row,
            "parent_bug_id": row["case_id"],
            "success": "1" if row["failure_mode"] == "success" else "0",
        })

    models = sorted({r["model_label"] for r in normalized})
    scopes = ("candidate_level", "first_candidate", "case_any_of_k")
    units = ("candidate", "case", "parent_bug")
    report_rows = []
    score_cache: dict[tuple[str, str], dict[str, list[int]]] = {}
    for model in models:
        model_rows = [r for r in normalized if r["model_label"] == model]
        for scope in scopes:
            scores = selected_scores(model_rows, scope)
            score_cache[(model, scope)] = scores
            for unit in units:
                value = metric(scores, unit)
                lo, hi = bootstrap_ci(scores, unit)
                observation_n = sum(len(v) for v in scores.values()) if unit == "candidate" else len(scores)
                report_rows.append({
                    "model": model,
                    "method": "frozen_dev_policy_router",
                    "selection_scope": scope,
                    "aggregation_unit": unit,
                    "k": 1 if scope == "first_candidate" else K,
                    "metric": "strict_primary_and_heldout_nonvacuous_success",
                    "value": f"{value:.8f}",
                    "observation_count": observation_n,
                    "candidate_count": 32 if scope == "candidate_level" else (16 if scope == "first_candidate" else 32),
                    "case_count": 16,
                    "parent_bug_count": 16,
                    "deduplicated": str(unit != "candidate").lower(),
                    "dedup_key": "none" if unit == "candidate" else ("case_id" if unit == "case" else "parent_bug_id"),
                    "parent_aggregation": "macro_mean; one sealed case per parent",
                    "overlap_status": "non_overlap",
                    "ci_level": "0.95",
                    "ci_lower": f"{lo:.8f}",
                    "ci_upper": f"{hi:.8f}",
                    "ci_method": "percentile_cluster_bootstrap",
                    "bootstrap_unit": "parent_bug_id",
                    "bootstrap_repetitions": BOOTSTRAPS,
                    "random_seed": SEED,
                    "sample_definition": "16 sealed pristine parents; frozen policy; primary+heldout correct/buggy; nonempty antecedent required",
                    "policy_refit_on_test": "false",
                })

    report_path = FREEZE / "formal_three_scope_report.csv"
    with report_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(report_rows[0]))
        writer.writeheader(); writer.writerows(report_rows)

    # Paired model comparison. McNemar is valid only for binary parent outcomes.
    comparisons = []
    left, right = models
    for scope in scopes:
        a, b = score_cache[(left, scope)], score_cache[(right, scope)]
        parent_scores_a = {p: sum(v) / len(v) for p, v in a.items()}
        parent_scores_b = {p: sum(v) / len(v) for p, v in b.items()}
        effect = sum(parent_scores_b[p] - parent_scores_a[p] for p in parents) / len(parents)
        if scope == "candidate_level":
            discord_b = discord_c = ""
            pvalue = ""
            applicability = "not_applicable_fractional_parent_scores"
        else:
            discord_b = sum(parent_scores_a[p] == 1 and parent_scores_b[p] == 0 for p in parents)
            discord_c = sum(parent_scores_a[p] == 0 and parent_scores_b[p] == 1 for p in parents)
            pvalue = f"{exact_mcnemar(discord_b, discord_c):.8f}"
            applicability = "exact_paired_parent_mcnemar"
        comparisons.append({
            "scope": scope, "k": 1 if scope == "first_candidate" else K,
            "model_a": left, "model_b": right, "parent_bug_count": 16,
            "effect_size": "paired_risk_difference_b_minus_a",
            "effect": f"{effect:.8f}", "discordant_a_only": discord_b,
            "discordant_b_only": discord_c, "mcnemar_p_exact_two_sided": pvalue,
            "mcnemar_status": applicability, "bootstrap_unit": "parent_bug_id",
            "overlap_status": "paired_same_16_nonoverlapping_parents",
        })
    comp_path = FREEZE / "paired_model_comparison.csv"
    with comp_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparisons[0]))
        writer.writeheader(); writer.writerows(comparisons)

    failure_counts = Counter(r["failure_mode"] for r in normalized)
    failure_path = FREEZE / "failure_mode_counts.csv"
    with failure_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["failure_mode", "count"])
        writer.writeheader()
        writer.writerows({"failure_mode": key, "count": value} for key, value in sorted(failure_counts.items()))

    source_hashes = {name: sha256(snapshot / name) for name in SOURCES}
    manifest = {
        "schema_version": 1,
        "frozen": True,
        "freeze_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "attestation": "Reports were computed from the frozen pristine test snapshot. Test outcomes were not used to refit, tune, or modify the locked dev policy.",
        "policy_refit_on_test": False,
        "policy_fit_scope": policy["fit_scope"],
        "policy_sha256_declared": policy["policy_sha256"],
        "dev_results_sha256_declared": policy["provenance"]["dev_results_sha256"],
        "sealed_test_sha256_declared": seal["seal_sha256"],
        "test_parent_count": 16,
        "case_count": 16,
        "candidate_count": 64,
        "k": K,
        "parent_overlap": False,
        "source_hashes": source_hashes,
        "report_hashes": {
            report_path.name: sha256(report_path),
            comp_path.name: sha256(comp_path),
            failure_path.name: sha256(failure_path),
        },
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest_path = FREEZE / "freeze_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "frozen": True, "rows": len(raw), "parents": len(parents),
        "raw_results_sha256": source_hashes["multi_model_results_raw.csv"],
        "report_sha256": sha256(report_path), "manifest_sha256": manifest["manifest_sha256"],
        "output": str(FREEZE),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
