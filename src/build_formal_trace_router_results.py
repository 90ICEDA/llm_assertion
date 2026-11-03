from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]


def truth(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def strict_success(row: dict[str, Any]) -> bool:
    return all(truth(row.get(key)) for key in (
        "heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous"
    ))


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values); position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high: return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def parent_bootstrap(rows: list[dict[str, Any]], value: Callable[[dict[str, Any]], float], iterations: int, seed: int, parent_equal: bool) -> tuple[float, float]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: groups[row["parent_bug_id"]].append(row)
    parents = sorted(groups); rng = random.Random(seed); estimates = []
    for _ in range(iterations):
        sampled = [rng.choice(parents) for _ in parents]
        if parent_equal:
            estimates.append(sum(sum(value(x) for x in groups[p]) / len(groups[p]) for p in sampled) / len(sampled))
        else:
            observations = [x for p in sampled for x in groups[p]]
            estimates.append(sum(value(x) for x in observations) / len(observations))
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def metric_row(name: str, rows: list[dict[str, Any]], iterations: int, seed: int) -> dict[str, Any]:
    rate = sum(float(row["success"]) for row in rows) / len(rows)
    low, high = parent_bootstrap(rows, lambda x: float(x["success"]), iterations, seed, False)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: groups[row["parent_bug_id"]].append(row)
    parent_rate = sum(sum(float(x["success"]) for x in group) / len(group) for group in groups.values()) / len(groups)
    parent_low, parent_high = parent_bootstrap(rows, lambda x: float(x["success"]), iterations, seed + 1, True)
    return {
        "metric": name, "model": "GPT/gpt-5.4", "k": 2, "sample_n": len(rows),
        "case_n": len({x["case_id"] for x in rows}), "parent_n": len(groups),
        "deduplicated": False, "overlap": False, "rate": rate,
        "parent_bootstrap_ci95_low": low, "parent_bootstrap_ci95_high": high,
        "parent_cluster_mean_rate": parent_rate, "parent_deduplicated": True,
        "parent_equal_bootstrap_ci95_low": parent_low, "parent_equal_bootstrap_ci95_high": parent_high,
    }


def exact_mcnemar_p(b: int, c: int) -> float:
    n = b + c
    if n == 0: return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", default=str(ROOT / "outputs/formal_trace_router/test_dispatch/generated/multi_model_results_raw.csv"))
    parser.add_argument("--routing", default=str(ROOT / "outputs/formal_trace_router/test_routing.csv"))
    parser.add_argument("--plan", default=str(ROOT / "outputs/formal_trace_router/test_dispatch/generation_dispatch_plan.csv"))
    parser.add_argument("--policy", default=str(ROOT / "outputs/formal_trace_router/locked_policy.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "outputs/formal_trace_router/formal_results"))
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260719)
    args = parser.parse_args()
    output_dir = Path(args.output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    with Path(args.evaluation).open(encoding="utf-8-sig", newline="") as handle: candidates = list(csv.DictReader(handle))
    with Path(args.routing).open(encoding="utf-8-sig", newline="") as handle: routing = list(csv.DictReader(handle))
    with Path(args.plan).open(encoding="utf-8-sig", newline="") as handle: plan = list(csv.DictReader(handle))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    route_lookup = {(x["model"], x["case_id"]): x for x in routing}
    for row in candidates:
        routed = route_lookup[(row["model_label"], row["case_id"])]
        row["parent_bug_id"] = routed["parent_bug_id"]; row["route"] = routed["route"]; row["success"] = strict_success(row)
    expected = sum(int(x["arm_k"]) for x in plan)
    unique_keys = {(x["model_label"], x["case_id"], x["method"], x["candidate_index"]) for x in candidates}
    if len(candidates) != expected or len(unique_keys) != expected: raise RuntimeError(f"Candidate completeness failed: {len(candidates)} rows, {len(unique_keys)} keys, expected {expected}")

    case_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates: case_groups[(row["model_label"], row["case_id"])].append(row)
    first_rows, case_rows = [], []
    for key, group in case_groups.items():
        route_row = route_lookup[key]
        arm_priority = {"spec_rtl_raw_trace": 0, "spec_rtl_temporal_relation_abstraction": 1}
        first = sorted(group, key=lambda x: (arm_priority.get(x["method"], 9), int(x["candidate_index"])))[0]
        base = {"model_label": key[0], "case_id": key[1], "parent_bug_id": route_row["parent_bug_id"], "route": route_row["route"]}
        first_rows.append({**base, "success": bool(first["success"]), "selected_method": first["method"], "selected_candidate_index": first["candidate_index"]})
        case_rows.append({**base, "success": any(bool(x["success"]) for x in group)})
    metric_rows = [
        metric_row("candidate_level", candidates, args.bootstrap, args.seed),
        metric_row("first_candidate", first_rows, args.bootstrap, args.seed + 10),
        metric_row("case_level_any_of_k", case_rows, args.bootstrap, args.seed + 20),
    ]
    with (output_dir / "router_metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metric_rows[0])); writer.writeheader(); writer.writerows(metric_rows)

    both_cases = [row for row in routing if row["route"] == "both"]
    paired_cases = []
    for route_row in both_cases:
        group = case_groups[(route_row["model"], route_row["case_id"])]
        raw = any(bool(x["success"]) for x in group if x["method"] == "spec_rtl_raw_trace")
        temporal = any(bool(x["success"]) for x in group if x["method"] == "spec_rtl_temporal_relation_abstraction")
        paired_cases.append({"case_id": route_row["case_id"], "parent_bug_id": route_row["parent_bug_id"], "raw_success": raw, "temporal_success": temporal})
    parent_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in paired_cases: parent_groups[row["parent_bug_id"]].append(row)
    canonical = []
    for parent, group in parent_groups.items():
        canonical.append(next((x for x in group if x["case_id"] == parent), sorted(group, key=lambda x: x["case_id"])[0]))
    b = sum(x["raw_success"] and not x["temporal_success"] for x in canonical)
    c = sum(x["temporal_success"] and not x["raw_success"] for x in canonical)
    raw_rate = sum(x["raw_success"] for x in canonical) / len(canonical); temporal_rate = sum(x["temporal_success"] for x in canonical) / len(canonical)
    rng = random.Random(args.seed + 100); effects = []
    for _ in range(args.bootstrap):
        sample = [rng.choice(canonical) for _ in canonical]
        effects.append(sum(float(x["temporal_success"]) - float(x["raw_success"]) for x in sample) / len(sample))
    comparison = {
        "scope": "both_route_only_canonical_parent", "model": "GPT/gpt-5.4", "arm_k": 1,
        "case_n": len(paired_cases), "parent_n": len(canonical), "deduplicated": True,
        "overlap": False, "raw_success_rate": raw_rate, "temporal_success_rate": temporal_rate,
        "discordant_raw_only_b": b, "discordant_temporal_only_c": c,
        "mcnemar_exact_p": exact_mcnemar_p(b, c), "effect_risk_difference_temporal_minus_raw": temporal_rate - raw_rate,
        "effect_ci95_low": percentile(effects, 0.025), "effect_ci95_high": percentile(effects, 0.975),
        "matched_odds_ratio_haldane": (c + 0.5) / (b + 0.5),
        "limitation": "Counterfactual always-raw/always-temporal baselines are unavailable outside route=both because fixed-budget dispatcher did not generate unselected arms.",
    }
    (output_dir / "raw_temporal_paired_comparison.json").write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    first_lookup = {x["case_id"]: x for x in first_rows}; any_lookup = {x["case_id"]: x for x in case_rows}
    all_parent_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in case_rows: all_parent_groups[row["parent_bug_id"]].append(row)
    canonical_budget = []
    for parent, group in all_parent_groups.items():
        chosen = next((x for x in group if x["case_id"] == parent), sorted(group, key=lambda x: x["case_id"])[0])
        canonical_budget.append({"parent_bug_id": parent, "case_id": chosen["case_id"], "first": bool(first_lookup[chosen["case_id"]]["success"]), "any_k": bool(any_lookup[chosen["case_id"]]["success"])})
    first_only = sum(x["first"] and not x["any_k"] for x in canonical_budget)
    any_only = sum(x["any_k"] and not x["first"] for x in canonical_budget)
    first_rate = sum(x["first"] for x in canonical_budget) / len(canonical_budget)
    any_rate = sum(x["any_k"] for x in canonical_budget) / len(canonical_budget)
    rng_budget = random.Random(args.seed + 200); budget_effects = []
    for _ in range(args.bootstrap):
        sample = [rng_budget.choice(canonical_budget) for _ in canonical_budget]
        budget_effects.append(sum(float(x["any_k"]) - float(x["first"]) for x in sample) / len(sample))
    budget_comparison = {
        "scope": "canonical_parent_first_candidate_vs_case_any_of_k", "model": "GPT/gpt-5.4", "k": 2,
        "parent_n": len(canonical_budget), "deduplicated": True, "overlap": False,
        "first_candidate_success_rate": first_rate, "case_any_of_k_success_rate": any_rate,
        "discordant_first_only_b": first_only, "discordant_any_of_k_only_c": any_only,
        "mcnemar_exact_p": exact_mcnemar_p(first_only, any_only),
        "effect_risk_difference_any_of_k_minus_first": any_rate - first_rate,
        "effect_ci95_low": percentile(budget_effects, 0.025), "effect_ci95_high": percentile(budget_effects, 0.975),
        "matched_odds_ratio_haldane": (any_only + 0.5) / (first_only + 0.5),
    }
    (output_dir / "first_vs_any_of_k_paired_comparison.json").write_text(json.dumps(budget_comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {
        "policy_sha256": policy["policy_sha256"], "policy_data_status": policy["data_status"],
        "model": "GPT/gpt-5.4", "k": 2, "candidate_n": len(candidates), "case_n": len(case_rows),
        "parent_n": len({x["parent_bug_id"] for x in case_rows}), "dev_test_parent_overlap": bool(set(policy["dev_parent_ids"]) & set(policy["test_parent_ids"])),
        "route_counts": Counter(x["route"] for x in routing), "metrics": metric_rows,
        "paired_raw_temporal": comparison, "paired_first_vs_any_of_k": budget_comparison,
    }
    (output_dir / "formal_router_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__": main()
