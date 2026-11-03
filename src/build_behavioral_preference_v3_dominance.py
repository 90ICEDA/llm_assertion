from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/probe_manifest.json"
OUT = ROOT / "outputs/behavioral_preference_pilot_v1/dominance_pairs_v3"
POLICIES = ("random_legal", "disagreement_guided")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stable(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def dominates(a: dict, b: dict) -> tuple[bool, bool, bool]:
    fp_a, fp_b = set(a["fp_probe_ids"]), set(b["fp_probe_ids"])
    tp_a, tp_b = set(a["tp_mutant_ids"]), set(b["tp_mutant_ids"])
    strict_fp = fp_a < fp_b
    strict_tp = tp_a > tp_b
    return fp_a <= fp_b and tp_a >= tp_b and (strict_fp or strict_tp), strict_fp, strict_tp


def main() -> None:
    manifest = json.loads(PROBES.read_text(encoding="utf-8"))
    if manifest.get("dominance_pairs_constructed") is not False:
        raise RuntimeError("source probe manifest must be sealed before pair construction")
    records = manifest["candidate_policy_records"]
    audits = {}
    for policy in POLICIES:
        grouped = defaultdict(list)
        for row in records:
            if row["probe_policy"] == policy:
                grouped[row["parent_bug_id"]].append(row)
        pairs = []
        comparable_ordered = 0
        incomparable_ordered = 0
        for parent, candidates in sorted(grouped.items()):
            if len(candidates) != 8:
                raise RuntimeError(f"{parent}/{policy}: expected 8 candidates, got {len(candidates)}")
            for chosen in candidates:
                for rejected in candidates:
                    if chosen["candidate_id"] == rejected["candidate_id"]:
                        continue
                    ok, strict_fp, strict_tp = dominates(chosen, rejected)
                    if not ok:
                        incomparable_ordered += 1
                        continue
                    comparable_ordered += 1
                    fp_c, fp_r = set(chosen["fp_probe_ids"]), set(rejected["fp_probe_ids"])
                    tp_c, tp_r = set(chosen["tp_mutant_ids"]), set(rejected["tp_mutant_ids"])
                    pairs.append({
                        "pair_id": stable(policy, parent, chosen["candidate_id"], rejected["candidate_id"]),
                        "probe_policy": policy,
                        "parent_bug_id": parent,
                        "chosen_id": chosen["candidate_id"],
                        "rejected_id": rejected["candidate_id"],
                        "chosen_sva_path": chosen["sva_path"],
                        "chosen_sva_sha256": chosen["sva_sha256"],
                        "rejected_sva_path": rejected["sva_path"],
                        "rejected_sva_sha256": rejected["sva_sha256"],
                        "chosen_prompt_path": chosen["prompt_path"],
                        "chosen_prompt_sha256": chosen["prompt_sha256"],
                        "rejected_prompt_path": rejected["prompt_path"],
                        "rejected_prompt_sha256": rejected["prompt_sha256"],
                        "chosen_generation_evidence_path": chosen["generation_evidence_path"],
                        "chosen_generation_evidence_sha256": chosen["generation_evidence_sha256"],
                        "rejected_generation_evidence_path": rejected["generation_evidence_path"],
                        "rejected_generation_evidence_sha256": rejected["generation_evidence_sha256"],
                        "chosen_fp": sorted(fp_c), "rejected_fp": sorted(fp_r),
                        "chosen_tp": sorted(tp_c), "rejected_tp": sorted(tp_r),
                        "fp_removed": sorted(fp_r - fp_c),
                        "tp_added": sorted(tp_c - tp_r),
                        "strict_fp": strict_fp, "strict_tp": strict_tp,
                        "dominance_predicate": {
                            "fp_chosen_subset_rejected": fp_c <= fp_r,
                            "tp_chosen_superset_rejected": tp_c >= tp_r,
                            "at_least_one_strict": strict_fp or strict_tp,
                        },
                    })
        out = OUT / f"{policy}_dominance_pairs.jsonl"
        write_jsonl(out, pairs)
        ids = [row["pair_id"] for row in pairs]
        audits[policy] = {
            "pair_count": len(pairs),
            "minimum_required": 300,
            "pass": len(pairs) >= 300,
            "parent_count": len(grouped),
            "candidate_count": sum(len(v) for v in grouped.values()),
            "strict_fp_only": sum(x["strict_fp"] and not x["strict_tp"] for x in pairs),
            "strict_tp_only": sum(x["strict_tp"] and not x["strict_fp"] for x in pairs),
            "strict_both": sum(x["strict_fp"] and x["strict_tp"] for x in pairs),
            "duplicate_pair_ids": len(ids) - len(set(ids)),
            "pair_file": str(out.relative_to(ROOT)).replace("\\", "/"),
            "pair_file_sha256": sha(out),
            "ordered_non_dominating_relations_omitted": incomparable_ordered,
        }
    audit = {
        "protocol": "strict_pareto_dominance_v3",
        "source_probe_manifest": str(PROBES.relative_to(ROOT)).replace("\\", "/"),
        "source_probe_manifest_sha256": sha(PROBES),
        "rules": ["FP_chosen subseteq FP_rejected", "TP_chosen superseteq TP_rejected", "at least one strict"],
        "cross_parent_comparisons": False,
        "cross_policy_comparisons": False,
        "forced_labels_for_incomparable_candidates": False,
        "policies": audits,
    }
    dump(OUT / "dominance_audit.json", audit)
    print(json.dumps({p: audits[p]["pair_count"] for p in POLICIES}, sort_keys=True))


if __name__ == "__main__":
    main()
