from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1"
FROZEN = BASE / "balanced_behavioral_objective_v1_frozen.json"
MODEL = ROOT / "outputs/checkpoints/Qwen3-8B"
TOTAL_BUDGET = 245760
SEED = 20260815
STRATUM_SHARES = {"joint_fp_tp": 0.50, "fp_only": 0.25, "tp_only": 0.25}


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_key(value: str, salt: str = ""):
    return hashlib.sha256(f"{SEED}\0{salt}\0{value}".encode()).hexdigest()


def response_cost(tokenizer, path: str) -> int:
    text = (ROOT / path).read_text(encoding="utf-8")
    return len(tokenizer.encode(text, add_special_tokens=False).ids) + 1  # supervised EOS


def attach_costs(tokenizer, edges, anchors):
    for row in edges:
        row["loss_tokens"] = response_cost(tokenizer, row["chosen_path"]) + response_cost(tokenizer, row["rejected_path"])
    for row in anchors:
        row["loss_tokens"] = response_cost(tokenizer, row["response_path"])


def balanced_edge_cycle(rows):
    by_parent = defaultdict(list)
    for row in sorted(rows, key=lambda x: stable_key(x["pair_id"], x["stratum"])):
        by_parent[row["parent_bug_id"]].append(row)
    capped = {}
    for parent, candidates in by_parent.items():
        degree = Counter(); accepted = []
        for row in candidates:
            if degree[row["chosen_id"]] >= 2 or degree[row["rejected_id"]] >= 2:
                continue
            accepted.append(row)
            degree[row["chosen_id"]] += 1; degree[row["rejected_id"]] += 1
        if accepted:
            capped[parent] = accepted
    per_parent = min(map(len, capped.values()))
    cycle = []
    for offset in range(per_parent):
        for parent in sorted(capped, key=lambda x: stable_key(x, f"parent-{offset}")):
            cycle.append(capped[parent][offset])
    degree = Counter()
    for row in cycle:
        degree[row["chosen_id"]] += 1; degree[row["rejected_id"]] += 1
    if max(degree.values()) > 2:
        raise RuntimeError("candidate degree cap violated in DPO cycle")
    return cycle, {"eligible_parents": len(capped), "records_per_parent_per_cycle": per_parent, "cycle_records": len(cycle), "cycle_max_candidate_degree": max(degree.values())}


def balanced_anchor_cycle(rows):
    by_parent = defaultdict(list)
    for row in sorted(rows, key=lambda x: stable_key(x["example_id"], "anchor")):
        by_parent[row["parent_bug_id"]].append(row)
    # A super-cycle contains the same number of selections per parent while
    # rotating through every eligible anchor owned by that parent. Parents
    # with one anchor repeat it across micro-cycles; parents with multiple
    # anchors alternate, preventing permanent starvation of valid anchors.
    per_parent = max(map(len, by_parent.values()))
    cycle = []
    for offset in range(per_parent):
        for parent in sorted(by_parent, key=lambda x: stable_key(x, f"anchor-parent-{offset}")):
            cycle.append(by_parent[parent][offset % len(by_parent[parent])])
    degree = Counter(row["example_id"] for row in cycle)
    if max(degree.values()) > 2:
        raise RuntimeError("anchor candidate degree cap violated in super-cycle")
    return cycle, {"eligible_parents": len(by_parent), "records_per_parent_per_cycle": per_parent, "cycle_records": len(cycle), "cycle_max_candidate_degree": max(degree.values()), "micro_cycles": per_parent, "rotation_uses_all_eligible_anchors": len(degree) == len(rows)}


def subset_for_exact(items, target):
    previous = [None] * (target + 1)
    previous[0] = (-1, -1)
    for index, row in enumerate(items):
        cost = row["loss_tokens"]
        for value in range(target - cost, -1, -1):
            if previous[value] is not None and previous[value + cost] is None:
                previous[value + cost] = (value, index)
        if previous[target] is not None:
            break
    if previous[target] is None:
        return None
    chosen, value = [], target
    while value:
        value, index = previous[value]
        chosen.append(items[index])
    return list(reversed(chosen))


def exact_cycle_schedule(cycle, target):
    cycle_tokens = sum(row["loss_tokens"] for row in cycle)
    maximum_full = target // cycle_tokens
    for full_cycles in range(maximum_full, -1, -1):
        remainder = target - full_cycles * cycle_tokens
        if remainder == 0:
            tail = []
        else:
            # Some small anchor pools need more than eight balanced cycles to
            # realize an exact integer token remainder (their item costs are
            # close but not identical). Each copy remains an independent
            # degree-capped cycle, so widening this bounded search does not
            # relax the frozen per-cycle constraint.
            copies = 64
            if remainder > copies * cycle_tokens:
                continue
            expanded = []
            for copy in range(copies):
                expanded.extend({**row, "_tail_cycle": copy} for row in cycle)
            tail = subset_for_exact(expanded, remainder)
            if tail is None:
                continue
        schedule = []
        for cycle_id in range(full_cycles):
            schedule.extend({**row, "schedule_cycle": cycle_id, "schedule_section": "full"} for row in cycle)
        for row in tail:
            value = {k: v for k, v in row.items() if k != "_tail_cycle"}
            value.update({"schedule_cycle": full_cycles + row.get("_tail_cycle", 0), "schedule_section": "exact_tail"})
            schedule.append(value)
        if sum(row["loss_tokens"] for row in schedule) == target:
            return schedule, {"target_tokens": target, "cycle_tokens": cycle_tokens, "full_cycles": full_cycles, "tail_records": len(tail)}
    raise RuntimeError(f"cannot exactly schedule target={target} from cycle costs={sorted({x['loss_tokens'] for x in cycle})}")


def schedule_variant(edges, anchors, fraction):
    anchor_target = int(TOTAL_BUDGET * fraction)
    dpo_total = TOTAL_BUDGET - anchor_target
    targets = {"anchor": anchor_target, **{name: int(dpo_total * share) for name, share in STRATUM_SHARES.items()}}
    if sum(targets.values()) != TOTAL_BUDGET:
        raise RuntimeError(f"non-exact bucket arithmetic: {targets}")
    buckets, cycle_audits = {}, {}
    anchor_cycle, cycle_audits["anchor"] = balanced_anchor_cycle(anchors)
    buckets["anchor"], cycle_audits["anchor_schedule"] = exact_cycle_schedule(anchor_cycle, targets["anchor"])
    for stratum in STRATUM_SHARES:
        cycle, cycle_audits[stratum] = balanced_edge_cycle([row for row in edges if row["stratum"] == stratum])
        buckets[stratum], cycle_audits[f"{stratum}_schedule"] = exact_cycle_schedule(cycle, targets[stratum])
    schedule = []
    for bucket in ("anchor", "joint_fp_tp", "fp_only", "tp_only"):
        for row in buckets[bucket]:
            schedule.append({**row, "objective_bucket": bucket})
    schedule.sort(key=lambda x: stable_key(str(x.get("pair_id", x.get("example_id"))) + str(x["schedule_cycle"]), "schedule-order"))
    anchor_counts = Counter(row["example_id"] for row in buckets["anchor"])
    anchor_tokens = Counter()
    anchor_parents = Counter()
    for row in buckets["anchor"]:
        anchor_tokens[row["example_id"]] += row["loss_tokens"]
        anchor_parents[row["parent_bug_id"]] += row["loss_tokens"]
    dpo_degree_by_cycle = defaultdict(Counter)
    for bucket in ("joint_fp_tp", "fp_only", "tp_only"):
        for row in buckets[bucket]:
            key = (bucket, row["schedule_cycle"])
            dpo_degree_by_cycle[key][row["chosen_id"]] += 1
            dpo_degree_by_cycle[key][row["rejected_id"]] += 1
    audit = {
        "anchor_fraction": fraction,
        "total_loss_tokens": sum(row["loss_tokens"] for row in schedule),
        "bucket_tokens": {name: sum(row["loss_tokens"] for row in rows) for name, rows in buckets.items()},
        "bucket_records": {name: len(rows) for name, rows in buckets.items()},
        "cycle_audits": cycle_audits,
        "effective_anchor_count": sum(count > 0 for count in anchor_counts.values()),
        "effective_anchor_parent_count": len(anchor_parents),
        "anchor_repetitions": dict(sorted(anchor_counts.items())),
        "unused_anchor_ids": sorted({row["example_id"] for row in anchors} - set(anchor_counts)),
        "max_anchor_example_token_share": max(anchor_tokens.values()) / anchor_target,
        "max_anchor_parent_token_share": max(anchor_parents.values()) / anchor_target,
        "max_dpo_candidate_degree_in_any_cycle": max(max(degree.values()) for degree in dpo_degree_by_cycle.values()),
        "exact_budget": sum(row["loss_tokens"] for row in schedule) == TOTAL_BUDGET,
    }
    if not audit["exact_budget"] or audit["max_dpo_candidate_degree_in_any_cycle"] > 2:
        raise RuntimeError("frozen scheduling constraint failed")
    return schedule, audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--materialize", action="store_true")
    args = parser.parse_args()
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    if frozen["status"] != "frozen_before_any_balanced_objective_training" or frozen["seed"] != SEED:
        raise RuntimeError("unexpected frozen objective")
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
    edges = read_jsonl(BASE / "dpo_edges_subtrain24.jsonl")
    anchors = read_jsonl(BASE / "safe_detect_anchors_subtrain24.jsonl")
    attach_costs(tokenizer, edges, anchors)
    reports = {}
    schedules = {}
    for fraction in frozen["anchor_fraction_candidates"]:
        schedule, report = schedule_variant(edges, anchors, fraction)
        variant = f"anchor_{int(fraction * 100):02d}"
        schedules[variant], reports[variant] = schedule, report
    result = {
        "status": "materialized" if args.materialize else "dry_run_pass",
        "objective_sha256": sha(FROZEN),
        "tokenizer_sha256": sha(MODEL / "tokenizer.json"),
        "total_loss_token_budget_per_variant": TOTAL_BUDGET,
        "variants": reports,
    }
    if args.materialize:
        schedule_dir = BASE / "token_schedules_v1"
        if schedule_dir.exists():
            raise RuntimeError("refusing to overwrite token_schedules_v1")
        schedule_dir.mkdir()
        for variant, schedule in schedules.items():
            path = schedule_dir / f"{variant}.jsonl"
            path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in schedule), encoding="utf-8")
        (schedule_dir / "schedule_audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        hashes = {path.name: sha(path) for path in sorted(schedule_dir.iterdir()) if path.is_file() and path.name != "SHA256SUMS.json"}
        (schedule_dir / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
