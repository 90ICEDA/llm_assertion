from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "outputs/behavioral_preference_pilot_v1"
V2 = ROOT / "outputs/behavioral_preference_pilot_v2"
SOURCE_DATA = V2 / "training_corpora_v2"
OUT = V2 / "balanced_behavioral_objective_v1"
KEYS = ("antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation")
ANCHOR_FRACTIONS = (0.10, 0.20, 0.25)
SEED = 20260815


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def category(row):
    if row["strict_fp"] and row["strict_tp"]:
        return "joint_fp_tp"
    if row["strict_fp"]:
        return "fp_only"
    if row["strict_tp"]:
        return "tp_only"
    raise RuntimeError(f"invalid dominance edge {row['pair_id']}")


def frozen_parent_split(parent_rows):
    ordered = sorted(parent_rows, key=lambda row: hashlib.sha256(f"{SEED}\0{row['parent_bug_id']}".encode()).hexdigest())
    dev, used_projects, used_families = [], set(), set()
    for project in sorted({row["source_project"] for row in ordered}):
        pick = next(row for row in ordered if row["source_project"] == project and row not in dev)
        dev.append(pick); used_projects.add(project); used_families.add(pick["bug_family"])
    while len(used_families) < 4:
        pick = next(row for row in ordered if row not in dev and row["bug_family"] not in used_families)
        dev.append(pick); used_projects.add(pick["source_project"]); used_families.add(pick["bug_family"])
    for row in ordered:
        if len(dev) == 6:
            break
        if row not in dev:
            dev.append(row); used_projects.add(row["source_project"]); used_families.add(row["bug_family"])
    dev_ids = {row["parent_bug_id"] for row in dev}
    subtrain = [row for row in parent_rows if row["parent_bug_id"] not in dev_ids]
    if len(dev) != 6 or len(subtrain) != 24 or len(used_projects) != 3 or len(used_families) < 4:
        raise RuntimeError("failed frozen 24/6 coverage constraints")
    return subtrain, dev


def main() -> None:
    if (OUT / "balanced_behavioral_objective_v1_frozen.json").exists():
        raise RuntimeError("objective is already frozen; refusing overwrite")
    with (V1 / "selected_train_parents.csv").open(encoding="utf-8-sig", newline="") as handle:
        parents = list(csv.DictReader(handle))
    subtrain, dev = frozen_parent_split(parents)
    subtrain_ids, dev_ids = {x["parent_bug_id"] for x in subtrain}, {x["parent_bug_id"] for x in dev}

    evidence = {}
    for path in (V1 / "sequential_generation_v3_pilot30").rglob("evidence.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        cid = f"{row['parent_bug_id']}__v3_slot_{int(row['slot']):02d}"
        evidence[cid] = row
    responses = {path.stem: path for path in (SOURCE_DATA / "responses").glob("*.json")}
    prompts = {path.parent.name: path for path in (SOURCE_DATA / "prompts").rglob("prompt.txt")}
    pairs = read_jsonl(V1 / "dominance_pairs_v3/disagreement_guided_dominance_pairs.jsonl")

    candidate_sets = {}
    enriched_edges = []
    for pair in pairs:
        for side in ("chosen", "rejected"):
            cid = pair[f"{side}_id"]
            value = (tuple(sorted(pair[f"{side}_fp"])), tuple(sorted(pair[f"{side}_tp"])))
            if cid in candidate_sets and candidate_sets[cid] != value:
                raise RuntimeError(f"inconsistent FP/TP sets for {cid}")
            candidate_sets[cid] = value
        parent = pair["parent_bug_id"]
        enriched_edges.append({
            "record_type": "dpo_edge", "pair_id": pair["pair_id"], "parent_bug_id": parent,
            "split": "subtrain" if parent in subtrain_ids else "dev", "stratum": category(pair),
            "chosen_id": pair["chosen_id"], "rejected_id": pair["rejected_id"],
            "prompt_path": str(prompts[parent].relative_to(ROOT)).replace("\\", "/"),
            "chosen_path": str(responses[pair["chosen_id"]].relative_to(ROOT)).replace("\\", "/"),
            "rejected_path": str(responses[pair["rejected_id"]].relative_to(ROOT)).replace("\\", "/"),
            "fp_removed_count": len(pair["fp_removed"]), "tp_added_count": len(pair["tp_added"]),
            "source_pair_sha256": hashlib.sha256(json.dumps(pair, sort_keys=True).encode()).hexdigest(),
        })

    anchors = []
    for cid, (fp, tp) in sorted(candidate_sets.items()):
        candidate = evidence[cid]
        if candidate["fixed_safe"] and candidate["target_detect"] and candidate["non_vacuous"] and not fp and tp:
            parent = candidate["parent_bug_id"]
            response = json.loads(responses[cid].read_text(encoding="utf-8"))
            if tuple(response) != KEYS:
                raise RuntimeError(f"noncanonical anchor response {cid}")
            anchors.append({
                "record_type": "sft_anchor", "example_id": cid, "parent_bug_id": parent,
                "split": "subtrain" if parent in subtrain_ids else "dev",
                "prompt_path": str(prompts[parent].relative_to(ROOT)).replace("\\", "/"),
                "response_path": str(responses[cid].relative_to(ROOT)).replace("\\", "/"),
                "fixed_safe": True, "target_detect": True, "non_vacuous": True,
                "fp_count": 0, "tp_count": len(tp),
            })

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "dpo_edges_all30.jsonl", enriched_edges)
    write_jsonl(OUT / "dpo_edges_subtrain24.jsonl", [x for x in enriched_edges if x["split"] == "subtrain"])
    write_jsonl(OUT / "dpo_edges_dev6.jsonl", [x for x in enriched_edges if x["split"] == "dev"])
    write_jsonl(OUT / "safe_detect_anchors_all30.jsonl", anchors)
    write_jsonl(OUT / "safe_detect_anchors_subtrain24.jsonl", [x for x in anchors if x["split"] == "subtrain"])
    write_jsonl(OUT / "safe_detect_anchors_dev6.jsonl", [x for x in anchors if x["split"] == "dev"])

    split_rows = []
    for split, rows in (("subtrain", subtrain), ("dev", dev)):
        for row in sorted(rows, key=lambda x: x["parent_bug_id"]):
            split_rows.append({"parent_bug_id": row["parent_bug_id"], "split": split, "source_project": row["source_project"], "bug_family": row["bug_family"]})
    write_jsonl(OUT / "parent_split_24_6.jsonl", split_rows)

    variants = []
    for fraction in ANCHOR_FRACTIONS:
        variant = {
            "variant_id": f"anchor_{int(fraction * 100):02d}",
            "anchor_loss_token_fraction": fraction,
            "dpo_loss_token_fraction": 1 - fraction,
            "subtrain_parent_count": 24,
            "dev_parent_count": 6,
            "dpo_edge_pool": str((OUT / "dpo_edges_subtrain24.jsonl").relative_to(ROOT)).replace("\\", "/"),
            "anchor_pool": str((OUT / "safe_detect_anchors_subtrain24.jsonl").relative_to(ROOT)).replace("\\", "/"),
        }
        variants.append(variant)
        (OUT / f"variant_{int(fraction * 100):02d}.json").write_text(json.dumps(variant, indent=2) + "\n", encoding="utf-8")

    stratum_counts = Counter(edge["stratum"] for edge in enriched_edges)
    subtrain_stratum_counts = Counter(edge["stratum"] for edge in enriched_edges if edge["split"] == "subtrain")
    frozen = {
        "status": "frozen_before_any_balanced_objective_training",
        "version": "balanced_behavioral_objective_v1",
        "seed": SEED,
        "source_candidate_count": 240,
        "source_dominance_pair_count": len(pairs),
        "source_dominance_sha256": sha(V1 / "dominance_pairs_v3/disagreement_guided_dominance_pairs.jsonl"),
        "output_protocol_frozen_unchanged": "pilot_v2_corrected_json_ast_eos_v1 + strict schema trie",
        "parent_split": {
            "subtrain": 24, "dev": 6, "all_projects_in_both": True,
            "dev_minimum_distinct_bug_families": 4,
            "selection": "SHA256(seed\\0parent_id) deterministic coverage-first; frozen before training",
            "split_manifest": str((OUT / "parent_split_24_6.jsonl").relative_to(ROOT)).replace("\\", "/"),
        },
        "loss_token_budget_per_variant": 245760,
        "sampling": {
            "parent": "uniform over eligible subtrain parents before edge selection",
            "stratum_loss_token_fractions": {"joint_fp_tp": 0.50, "fp_only": 0.25, "tp_only": 0.25},
            "within_stratum": "uniform over unique directed candidate-id edges",
            "candidate_degree_cap_per_schedule_cycle": 2,
            "padding": "batch size 1; no padding; exact attention mask",
            "response_eos_required": True,
        },
        "anchor_eligibility": "fixed_safe && target_detect && non_vacuous && FP empty && TP nonempty on train evidence only",
        "anchor_fraction_candidates": list(ANCHOR_FRACTIONS),
        "dev_selection": {
            "generation": "same strict-trie greedy Top-1 protocol; one generation per adapter/dev query; no repair/reranker/selector",
            "constraints": ["Fixed-Safe >= scalar_score_dpo dev baseline", "Target Detect >= full_disagreement_dominance_dpo dev baseline"],
            "ranking": ["highest SCS@1", "highest Fixed-Safe", "highest Target Detect", "smallest anchor fraction"],
            "no_eligible_variant": "NO-GO; do not refit all30 and do not access frozen OOD outcomes",
        },
        "phase_b_refit": "after dev selection only, refit selected variant on all 30 parents with the same 245760 response-loss tokens, then executable smoke, then one frozen OOD run",
        "forbidden": ["using current or future OOD outcomes for variant selection", "case-specific OOD tuning", "changing the 48-query universe", "relaxing strict Pareto labels"],
        "variants": variants,
        "inventory": {"all_edges": dict(stratum_counts), "subtrain_edges": dict(subtrain_stratum_counts), "safe_detect_anchors_all30": len(anchors), "safe_detect_anchors_subtrain24": sum(x["split"] == "subtrain" for x in anchors), "safe_detect_anchors_dev6": sum(x["split"] == "dev" for x in anchors)},
    }
    frozen_path = OUT / "balanced_behavioral_objective_v1_frozen.json"
    frozen_path.write_text(json.dumps(frozen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path) for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"}
    (OUT / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "frozen", "objective_sha256": sha(frozen_path), "subtrain_parents": 24, "dev_parents": 6, "inventory": frozen["inventory"]}, sort_keys=True))


if __name__ == "__main__":
    main()
