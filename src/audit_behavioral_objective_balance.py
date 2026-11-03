from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "outputs/behavioral_preference_pilot_v1"
V2 = ROOT / "outputs/behavioral_preference_pilot_v2"
OUT = V2 / "behavioral_objective_balance_audit_v1"


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def candidate_evidence():
    result = {}
    for path in (V1 / "sequential_generation_v3_pilot30").rglob("evidence.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        key = f"{row['parent_bug_id']}__v3_slot_{int(row['slot']):02d}"
        result[key] = row
    if len(result) != 240:
        raise RuntimeError(f"expected 240 candidates, got {len(result)}")
    return result


def category(row):
    if row["strict_fp"] and row["strict_tp"]:
        return "joint_fp_tp"
    if row["strict_fp"]:
        return "fp_only"
    if row["strict_tp"]:
        return "tp_only"
    raise RuntimeError(f"non-strict pair {row['pair_id']}")


def summarize_pairs(rows, evidence):
    strata = defaultdict(lambda: Counter())
    parent_strata = defaultdict(Counter)
    chosen_degree, rejected_degree = Counter(), Counter()
    for row in rows:
        cat = category(row)
        chosen = evidence[row["chosen_id"]]
        s = strata[cat]
        s["pairs"] += 1
        s["fp_removed"] += len(row["fp_removed"])
        s["tp_added"] += len(row["tp_added"])
        s["chosen_fixed_safe"] += bool(chosen["fixed_safe"])
        s["chosen_target_detect"] += bool(chosen["target_detect"])
        s["chosen_joint_safe_detect"] += bool(chosen["fixed_safe"] and chosen["target_detect"])
        s["chosen_zero_fp"] += not row["chosen_fp"]
        s["chosen_nonzero_tp"] += bool(row["chosen_tp"])
        parent_strata[row["parent_bug_id"]][cat] += 1
        chosen_degree[row["chosen_id"]] += 1
        rejected_degree[row["rejected_id"]] += 1
    normalized = {}
    for cat in ("fp_only", "tp_only", "joint_fp_tp"):
        s = strata[cat]
        n = s["pairs"]
        normalized[cat] = {
            **dict(s),
            "fraction": n / len(rows),
            "mean_fp_removed": s["fp_removed"] / n if n else None,
            "mean_tp_added": s["tp_added"] / n if n else None,
            "chosen_fixed_safe_rate": s["chosen_fixed_safe"] / n if n else None,
            "chosen_target_detect_rate": s["chosen_target_detect"] / n if n else None,
            "chosen_joint_safe_detect_rate": s["chosen_joint_safe_detect"] / n if n else None,
        }
    return {
        "pair_count": len(rows),
        "strata": normalized,
        "parents_with_each_stratum": {cat: sum(counter[cat] > 0 for counter in parent_strata.values()) for cat in ("fp_only", "tp_only", "joint_fp_tp")},
        "unique_chosen": len(chosen_degree),
        "unique_rejected": len(rejected_degree),
        "max_chosen_degree": max(chosen_degree.values()),
        "max_rejected_degree": max(rejected_degree.values()),
    }


def main():
    evidence = candidate_evidence()
    policies = {}
    for policy, filename in (("random_legal", "random_legal_dominance_pairs.jsonl"), ("disagreement_guided", "disagreement_guided_dominance_pairs.jsonl")):
        rows = read_jsonl(V1 / "dominance_pairs_v3" / filename)
        policies[policy] = summarize_pairs(rows, evidence)
    metrics = json.loads((V2 / "frozen_top1_ast_v2/execution_evaluation_v1/frozen_top1_metrics.json").read_text(encoding="utf-8"))
    observed = {}
    for split in ("unseen_parent", "unseen_bug_family", "union_overview"):
        methods = metrics["summaries"][split]["methods"]
        observed[split] = {
            name: {key: methods[name][key] for key in ("SCS@1", "Fixed-Safe", "Target Detect", "Family Recall", "Non-vacuity", "TOR")}
            for name in ("random_probe_dominance_dpo", "full_disagreement_dominance_dpo")
        }
    proposal = {
        "status": "proposal_not_frozen_not_authorized_for_training",
        "name": "parent_uniform_stratified_pareto_dpo_with_safe_detect_anchor",
        "invariants": [
            "labels remain strict same-parent Pareto dominance; no incomparable pair is introduced",
            "only train-parent FP/TP and fixed execution evidence may be used",
            "no held-out query, outcome, metric, or test-case-specific tuning",
            "AST/schema/EOS/trie protocol remains unchanged",
            "total response-loss token budget, base checkpoint, seed, optimizer, and adapter configuration remain unchanged",
        ],
        "proposed_sampling": {
            "parent_sampling": "uniform over the 30 train parents before pair sampling",
            "strata": {"joint_fp_tp": 0.50, "fp_only": 0.25, "tp_only": 0.25},
            "within_stratum": "uniform over unique directed candidate-id edges; cap repeated chosen or rejected candidate degree per schedule cycle",
        },
        "safe_detect_anchor": "reserve a frozen fraction of loss tokens for canonical AST SFT anchors whose train evidence has fixed_safe=true, target_detect=true, non_vacuous=true, empty FP, and non-empty TP",
        "anchor_fraction_candidates": [0.10, 0.20, 0.25],
        "selection_rule_before_ood": "choose one anchor fraction using a parent-held-out train/dev split and a frozen joint criterion; OOD outcomes remain sealed",
        "required_pre_ood_gate": "on held-out train parents, Fixed-Safe must not fall below scalar-score DPO while Target Detect must not fall below full disagreement DPO; then run the same three-parent 8/8 executable smoke",
    }
    report = {
        "status": "complete",
        "candidate_count": len(evidence),
        "policies": policies,
        "observed_frozen_ood_tradeoff": observed,
        "diagnosis": "guided pairs are dominated by FP-only improvements, while random-probe training is detection-heavy and unsafe; pair count alone does not balance behavioral gradients",
        "proposal": proposal,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "behavioral_objective_balance_audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Behavioral objective balance audit", "", "The current objective is imbalanced; no new objective is frozen yet.", ""]
    for policy, result in policies.items():
        lines += [f"## {policy}", "", "| Stratum | Pairs | Share | Mean FP removed | Mean TP added | Chosen Fixed-Safe | Chosen Target Detect | Chosen joint |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for cat, value in result["strata"].items():
            lines.append(f"| {cat} | {value['pairs']} | {value['fraction']:.2%} | {value['mean_fp_removed']:.2f} | {value['mean_tp_added']:.2f} | {value['chosen_fixed_safe_rate']:.2%} | {value['chosen_target_detect_rate']:.2%} | {value['chosen_joint_safe_detect_rate']:.2%} |")
        lines.append("")
    lines += ["## Proposed next objective", "", "This is a proposal requiring an explicit freeze before training.", "", "- Parent-uniform sampling.", "- 50% joint FP+TP, 25% FP-only, 25% TP-only strict Pareto edges.", "- Add a small safe+detect canonical-AST anchor budget, selected only on a train-parent dev split.", "- Keep the output protocol and OOD universe unchanged.", ""]
    (OUT / "behavioral_objective_balance_audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "complete", "guided": policies["disagreement_guided"], "proposal_status": proposal["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
