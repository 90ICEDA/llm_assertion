from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
RAW = "spec_rtl_raw_trace"
TEMPORAL = "spec_rtl_temporal_relation_abstraction"
CONTROL_TOKENS = ("clk", "rst", "reset", "enable", "en_", "valid", "ready", "req", "ack", "clear", "clr", "qe", "state", "mode", "full", "empty")
DELAY_RE = re.compile(r"\b(?:next|following|same)\s+cycle\b|\b(?:one|two|three|\d+)\s+cycles?\b|\bdelay(?:ed)?\b", re.I)


def parent_id(case_id: str) -> str:
    match = re.search(r"_from_(case\d+_.+)$", case_id)
    return match.group(1) if match else case_id


def parse_trace(path: Path) -> list[dict[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"cycle\s+(\d+):\s*(.*)", line.strip(), re.I)
        if not match: continue
        row = {"cycle": match.group(1)}
        for piece in match.group(2).split(","):
            if "=" in piece:
                key, value = piece.strip().split("=", 1); row[key.strip()] = value.strip()
        rows.append(row)
    return rows


def trace_features(cases_root: Path, case_meta: dict[str, Any]) -> dict[str, Any]:
    case_id = case_meta["name"]; experiment = cases_root / case_id / "experiment"
    good, bad = parse_trace(experiment / "trace_good.txt"), parse_trace(experiment / "trace_bad.txt")
    differences = []
    for g, b in zip(good, bad):
        names = sorted(set(g) | set(b) - {"cycle"})
        differing = [name for name in names if g.get(name) != b.get(name)]
        if differing: differences.append((int(g["cycle"]), differing))
    first = differences[0][0] if differences else len(good)
    window = 0
    if differences:
        expected = first
        for cycle, _ in differences:
            if cycle != expected: break
            window += 1; expected += 1
    differing_signals = sorted({name for _, names in differences for name in names})
    key_signals = [str(x) for x in case_meta.get("key_signals", [])]
    control_count = sum(any(token in name.lower() for token in CONTROL_TOKENS) for name in key_signals)
    ratio = control_count / len(key_signals) if key_signals else 0.0
    spec = str(case_meta.get("spec", ""))
    temporal_type = str((case_meta.get("golden_sva") or {}).get("temporal_type", ""))
    cross_cycle = case_meta.get("bug_class") == "temporal_cross_cycle" or "cross-cycle" in temporal_type.lower()
    return {
        "case_id": case_id, "parent_bug_id": parent_id(case_id), "trace_length": max(len(good), len(bad)),
        "first_divergence_distance": first, "divergence_window": window,
        "differing_signal_count": len(differing_signals), "is_cross_cycle": bool(cross_cycle),
        "has_explicit_delay": bool(DELAY_RE.search(spec + " " + temporal_type)),
        "control_signal_ratio": round(ratio, 6), "data_signal_ratio": round(1.0 - ratio, 6),
        "differing_signals": ",".join(differing_signals),
    }


def truth(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def candidate_success(row: dict[str, str]) -> bool:
    return all(truth(row.get(key)) for key in ("heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous"))


def load_outcomes(path: Path) -> dict[tuple[str, str], dict[str, bool]]:
    outcomes: dict[tuple[str, str], dict[str, bool]] = defaultdict(lambda: {"raw": False, "temporal": False})
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["method"] not in {RAW, TEMPORAL}: continue
            arm = "raw" if row["method"] == RAW else "temporal"
            outcomes[(row["model_label"], row["case_id"])][arm] |= candidate_success(row)
    return dict(outcomes)


def split_parents(features: list[dict[str, Any]], dev_fraction: float) -> tuple[list[str], list[str]]:
    parents = sorted({x["parent_bug_id"] for x in features}, key=lambda x: hashlib.sha256(x.encode()).hexdigest())
    cut = max(1, min(len(parents) - 1, round(len(parents) * dev_fraction)))
    return sorted(parents[:cut]), sorted(parents[cut:])


def route(features: dict[str, Any], model: str, params: dict[str, Any]) -> tuple[str, str]:
    temporal_signal = (
        features["is_cross_cycle"] or features["has_explicit_delay"]
        or features["first_divergence_distance"] >= params["late_divergence_threshold"]
        or features["divergence_window"] >= params["long_window_threshold"]
    )
    raw_signal = (
        features["trace_length"] <= params["short_trace_threshold"]
        and features["differing_signal_count"] <= params["few_difference_signals_threshold"]
        and features["control_signal_ratio"] <= params["max_control_ratio_for_raw"]
    )
    if temporal_signal and raw_signal:
        decision = params["model_overlap_resolution"].get(model, "both")
        reason = "both feature groups fired; resolved by frozen model-type rule"
    elif temporal_signal:
        decision, reason = "temporal", "cross-cycle/delay/late-or-long divergence features fired"
    elif raw_signal:
        decision, reason = "raw", "short trace with few differences and data-heavy signals"
    else:
        decision, reason = "both", "neither arm has a sufficiently strong frozen feature signal"
    return decision, reason


def decision_success(decision: str, outcome: dict[str, bool]) -> bool:
    return outcome["raw"] if decision == "raw" else outcome["temporal"] if decision == "temporal" else outcome["raw"] or outcome["temporal"]


def canonical_hash(payload: dict[str, Any]) -> str:
    clean = dict(payload); clean.pop("policy_sha256", None)
    return hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fit(args: argparse.Namespace) -> None:
    cases_root, results_path = Path(args.root).resolve(), Path(args.results).resolve()
    manifest_path = cases_root / "case_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]
    features = [trace_features(cases_root, item) for item in manifest]
    dev_parents, test_parents = split_parents(features, args.dev_fraction)
    outcomes = load_outcomes(results_path); models = sorted({key[0] for key in outcomes})
    dev = [x for x in features if x["parent_bug_id"] in set(dev_parents)]
    grids = itertools.product((6, 8, 10), (2, 3, 4), (2, 3, 4), (1, 2), (0.4, 0.6, 0.8), itertools.product(("raw", "temporal", "both"), repeat=len(models)))
    best = None
    for short_len, late, window, few, control_ratio, resolutions in grids:
        params = {
            "short_trace_threshold": short_len, "late_divergence_threshold": late,
            "long_window_threshold": window, "few_difference_signals_threshold": few,
            "max_control_ratio_for_raw": control_ratio,
            "model_overlap_resolution": dict(zip(models, resolutions)),
        }
        scores, both_count = [], 0
        for feature in dev:
            for model in models:
                outcome = outcomes.get((model, feature["case_id"]));
                if not outcome: continue
                decision, _ = route(feature, model, params); both_count += decision == "both"
                scores.append(decision_success(decision, outcome))
        accuracy = sum(scores) / len(scores); utility = accuracy - args.both_penalty * (both_count / len(scores))
        key = (utility, accuracy, -both_count, json.dumps(params, sort_keys=True))
        if best is None or key > best[0]: best = (key, params, accuracy, both_count, len(scores))
    _, params, accuracy, both_count, n = best
    policy = {
        "schema_version": 1, "locked": True, "fit_scope": "dev_parent_only",
        "data_status": args.data_status, "k": 2,
        "success_metric": "case_level_any_of_k_heldout", "dev_fraction": args.dev_fraction,
        "dev_parent_ids": dev_parents, "test_parent_ids": test_parents,
        "feature_names": ["trace_length", "first_divergence_distance", "divergence_window", "differing_signal_count", "is_cross_cycle", "has_explicit_delay", "control_signal_ratio", "data_signal_ratio", "model_type"],
        "params": params, "dev_model_case_n": n, "dev_routed_success_rate": accuracy,
        "dev_both_count": both_count, "both_penalty": args.both_penalty,
        "provenance": {
            "fit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "dev_results_path": str(results_path), "dev_results_sha256": file_sha256(results_path),
            "dev_results_manifest_path": str(Path(args.results_manifest).resolve()),
            "dev_results_manifest_sha256": file_sha256(Path(args.results_manifest).resolve()),
            "temporal_summaries_path": str(Path(args.temporal_summaries).resolve()),
            "temporal_summaries_sha256": file_sha256(Path(args.temporal_summaries).resolve()),
            "manifest_path": str(manifest_path), "manifest_sha256": file_sha256(manifest_path),
            "router_code_path": str(Path(__file__).resolve()), "router_code_sha256": file_sha256(Path(__file__).resolve()),
            "split_sha256": hashlib.sha256(json.dumps({"dev": dev_parents, "test": test_parents}, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "fit_argv": list(__import__("sys").argv), "feature_extractor_version": "trace_router_features_v1",
        },
    }
    policy["policy_sha256"] = canonical_hash(policy)
    output = Path(args.policy).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(policy, indent=2, ensure_ascii=False))


def run_test(args: argparse.Namespace) -> None:
    cases_root, policy_path = Path(args.root).resolve(), Path(args.policy).resolve()
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not policy.get("locked") or policy.get("policy_sha256") != canonical_hash(policy):
        raise RuntimeError("Policy is not locked or its SHA-256 does not match.")
    provenance = policy.get("provenance") or {}
    for path_key, hash_key in (("manifest_path", "manifest_sha256"), ("router_code_path", "router_code_sha256"), ("temporal_summaries_path", "temporal_summaries_sha256"), ("dev_results_path", "dev_results_sha256"), ("dev_results_manifest_path", "dev_results_manifest_sha256")):
        path = Path(provenance.get(path_key, ""))
        if not path.exists() or file_sha256(path) != provenance.get(hash_key):
            raise RuntimeError(f"Policy provenance mismatch: {path_key}")
    manifest = json.loads((cases_root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]
    test_parent_set = set(policy["test_parent_ids"]); models = sorted(policy["params"]["model_overlap_resolution"])
    rows = []
    for item in manifest:
        feature = trace_features(cases_root, item)
        if feature["parent_bug_id"] not in test_parent_set: continue
        for model in models:
            decision, reason = route(feature, model, policy["params"])
            rows.append({"model": model, **feature, "route": decision, "route_reason": reason, "policy_sha256": policy["policy_sha256"]})
    output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(f"test routing rows: {len(rows)} -> {output}")


def evaluate_test(args: argparse.Namespace) -> None:
    policy = json.loads(Path(args.policy).resolve().read_text(encoding="utf-8"))
    if policy.get("policy_sha256") != canonical_hash(policy): raise RuntimeError("Policy hash mismatch")
    outcomes = load_outcomes(Path(args.results).resolve())
    with Path(args.routing).resolve().open(encoding="utf-8-sig", newline="") as handle: rows = list(csv.DictReader(handle))
    evaluated = []
    for row in rows:
        outcome = outcomes[(row["model"], row["case_id"])]
        evaluated.append({**row, "raw_success": outcome["raw"], "temporal_success": outcome["temporal"], "routed_success": decision_success(row["route"], outcome)})
    output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evaluated[0])); writer.writeheader(); writer.writerows(evaluated)
    by_model = {}
    for model in sorted({x["model"] for x in evaluated}):
        sub = [x for x in evaluated if x["model"] == model]
        parent_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in sub: parent_groups[row["parent_bug_id"]].append(row)
        parent_cluster_mean = sum(
            sum(bool(x["routed_success"]) for x in group) / len(group)
            for group in parent_groups.values()
        ) / len(parent_groups)
        by_model[model] = {
            "k": policy["k"], "model_case_n": len(sub), "case_n": len({x["case_id"] for x in sub}),
            "parent_n": len(parent_groups), "deduplicated": False, "overlap": False,
            "case_level_any_of_k_success_rate": sum(bool(x["routed_success"]) for x in sub) / len(sub),
            "parent_cluster_mean_success_rate": parent_cluster_mean,
            "route_counts": Counter(x["route"] for x in sub),
        }
    summary = {
        "policy_sha256": policy["policy_sha256"], "model": "reported separately in by_model",
        "k": policy["k"], "test_model_case_n": len(evaluated),
        "test_case_n": len({x["case_id"] for x in evaluated}),
        "test_parent_n": len(set(x["parent_bug_id"] for x in evaluated)),
        "parent_overlap_between_dev_test": bool(set(policy["dev_parent_ids"]) & set(policy["test_parent_ids"])),
        "route_counts": Counter(x["route"] for x in evaluated),
        "routed_success_rate": sum(bool(x["routed_success"]) for x in evaluated) / len(evaluated),
        "by_model": by_model, "data_status": policy["data_status"],
    }
    summary_path = output.with_suffix(".summary.json"); summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit a dev-only trace router, lock it, then route/evaluate test without retuning.")
    parser.add_argument("command", choices=("fit-lock", "route-test", "evaluate-test"))
    parser.add_argument("--root", default=str(ROOT / "rtl_cases_real_scale120"))
    parser.add_argument("--results", default=str(ROOT / "outputs/scale120_trace_representation_ablation_data/multi_model_results_raw.csv"))
    parser.add_argument("--policy", default=str(ROOT / "outputs/trace_router/locked_policy.json"))
    parser.add_argument("--routing", default=str(ROOT / "outputs/trace_router/test_routing.csv"))
    parser.add_argument("--output", default=str(ROOT / "outputs/trace_router/test_routing.csv"))
    parser.add_argument("--dev-fraction", type=float, default=0.6)
    parser.add_argument("--both-penalty", type=float, default=0.05)
    parser.add_argument("--data-status", choices=("legacy_temporal_noncompliant_prototype", "formal_compliant"), default="legacy_temporal_noncompliant_prototype")
    parser.add_argument("--temporal-summaries", default=str(ROOT / "outputs/formal_temporal_abstractions/temporal_abstractions.json"))
    parser.add_argument("--results-manifest", default=str(ROOT / "outputs/formal_multimodel/combined_dev_formal/merge_manifest.json"))
    args = parser.parse_args()
    if args.command == "fit-lock": fit(args)
    elif args.command == "route-test": run_test(args)
    else: evaluate_test(args)


if __name__ == "__main__": main()
