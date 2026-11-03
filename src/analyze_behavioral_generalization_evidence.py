import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "outputs/behavioral_preference_pilot_v1/behavioral_probes_v3"
GEN = ROOT / "outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30"
OUT = ROOT / "outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parents = sorted(p for p in PROBES.iterdir() if p.is_dir())
    family_selected = {p: Counter() for p in ("random_legal", "disagreement_guided")}
    family_dist = {p: Counter() for p in family_selected}
    signatures = {p: set() for p in family_selected}
    primary = {}
    variant_fail = defaultdict(Counter)
    variant_fail_candidates = defaultdict(lambda: defaultdict(set))
    examples = defaultdict(list)
    incomparability = {}

    for parent in parents:
        pr = load(parent / "parent_result.json")
        pool = {x["probe_id"]: x for x in load(parent / "probe_pool.json")["probes"]}
        by_policy = defaultdict(dict)
        for row in pr["candidate_sets"]:
            by_policy[row["probe_policy"]][row["candidate_id"]] = (
                frozenset(row["fp_probe_ids"]), frozenset(row["tp_mutant_ids"])
            )
            signatures[row["probe_policy"]].add((tuple(sorted(row["fp_probe_ids"])), tuple(sorted(row["tp_mutant_ids"]))))
        for policy, ids in pr["policies"].items():
            for pid in ids:
                fams = {t["family"] for t in pool[pid].get("transformations", [])} or {"untransformed"}
                for fam in fams:
                    family_selected[policy][fam] += 1
            selected_rows = [x for x in pr["candidate_sets"] if x["probe_policy"] == policy]
            for row in selected_rows:
                for pid in row["distinguishing_probe_ids"]:
                    fams = {t["family"] for t in pool[pid].get("transformations", [])} or {"untransformed"}
                    for fam in fams:
                        family_dist[policy][fam] += 1

        # strict dominance vs equal signature vs crossing trade-off
        for policy, rows in by_policy.items():
            counts = Counter()
            for (_, (f1, t1)), (_, (f2, t2)) in itertools.combinations(rows.items(), 2):
                if f1 == f2 and t1 == t2:
                    counts["equal_signature"] += 1
                elif ((f1 <= f2 and t1 >= t2) or (f2 <= f1 and t2 >= t1)):
                    counts["strict_dominance"] += 1
                else:
                    counts["crossing_incomparable"] += 1
            key = policy
            incomparability.setdefault(key, Counter()).update(counts)

        # primary means fixed-safe + target-detect + non-vacuous on original TB.
        for evp in (GEN / parent.name).glob("slot_*/attempt_*/evidence.json"):
            ev = load(evp)
            cid = f"{parent.name}__v3_slot_{ev['slot']:02d}"
            if ev.get("icarus_compile_ok") and ev.get("fixed_safe") and ev.get("target_detect") and ev.get("non_vacuous"):
                primary[cid] = str(evp.relative_to(ROOT))
                # Use the full 64-probe pool so attribution is not policy-selection dependent.
                for pid, probe in pool.items():
                    rp = parent / "runs" / pid / cid / "result.json"
                    if not rp.exists():
                        continue
                    rr = load(rp)
                    target_like = probe.get("source_label") in {"target", "holdout"}
                    if rr.get("fp") or (target_like and not rr.get("tp")):
                        # Legal-source failures are FP; target/mutant misses are lack of TP.
                        failure = "legal_FP" if rr.get("fp") else "target_or_family_miss"
                        fams = {t["family"] for t in probe.get("transformations", [])} or {"untransformed"}
                        for fam in fams:
                            variant_fail[failure][fam] += 1
                            variant_fail_candidates[failure][fam].add(cid)
                            if len(examples[(failure, fam)]) < 3:
                                examples[(failure, fam)].append({
                                    "candidate_id": cid, "probe_id": pid,
                                    "source_label": probe.get("source_label"),
                                    "evidence": str(rp.relative_to(ROOT)),
                                })

    inc_out = {}
    total_unordered = len(parents) * 28
    for policy, c in incomparability.items():
        unlabeled = c["equal_signature"] + c["crossing_incomparable"]
        inc_out[policy] = dict(c) | {
            "total_unordered": total_unordered,
            "unlabeled_fraction": unlabeled / total_unordered,
            "crossing_incomparable_fraction": c["crossing_incomparable"] / total_unordered,
            "equal_signature_fraction": c["equal_signature"] / total_unordered,
        }

    # Existing frozen Top-1 metrics are the valid behavioral-abstraction test.
    v2_metrics = load(ROOT / "outputs/behavioral_preference_pilot_v2/frozen_top1_ast_v2/execution_evaluation_v1/frozen_top1_metrics.json")
    phase_b = load(ROOT / "outputs/phase_b_ood_eval_v1/phase_b_ood_metrics_and_decision.json")
    repair = load(ROOT / "outputs/019ed9f6-87cf-7830-adb8-595fe2ae140d/antecedent_repair_data/antecedent_repair_summary.json")
    result = {
        "status": "descriptive_posthoc_analysis_no_frozen_result_modified",
        "definitions": {
            "primary_pass": "compile && fixed_safe && target_detect && non_vacuous on original parent TB",
            "unlabeled_pair": "equal FP/TP signature or crossing/non-nested FP/TP sets",
            "failure_mode_proxy": "probe transformation family; counts are candidate-probe-family incidences and may overlap",
        },
        "primary_pass_candidate_count": len(primary),
        "primary_pass_evidence": primary,
        "primary_pass_variant_failures": {k: dict(v.most_common()) for k, v in variant_fail.items()},
        "primary_pass_variant_failure_candidate_counts": {
            failure: {fam: len(ids) for fam, ids in families.items()}
            for failure, families in variant_fail_candidates.items()
        },
        "primary_pass_variant_failure_examples": {f"{k[0]}::{k[1]}": v for k, v in examples.items()},
        "pair_comparability": inc_out,
        "probe_policy": {
            p: {
                "selected_probe_family_counts": dict(family_selected[p].most_common()),
                "distinguishing_candidate_probe_family_incidences": dict(family_dist[p].most_common()),
                "unique_fp_tp_signatures": len(signatures[p]),
            } for p in family_selected
        },
        "frozen_top1_metrics": v2_metrics["summaries"],
        "phase_b_metrics": phase_b["summaries"],
        "repair_summary": repair,
        "interpretation_limits": [
            "The frozen 48-query manifest has no explicit signal-renaming or parameter-change stratum labels.",
            "Probe transformation families measure behavioral sensitivity, not a causal decomposition of model internals.",
            "Text-diagnosis causality cannot be identified without randomized diagnosis-label intervention at fixed behavioral evidence.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "pass", "primary_pass_candidates": len(primary),
        "random_unlabeled_fraction": inc_out["random_legal"]["unlabeled_fraction"],
        "disagreement_unlabeled_fraction": inc_out["disagreement_guided"]["unlabeled_fraction"],
        "output": str(OUT.relative_to(ROOT)),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
