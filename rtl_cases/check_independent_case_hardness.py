#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


REQUIRED_WEAK_KINDS = {
    "single_cycle_implication",
    "final_output_only",
    "delay_removed",
    "antecedent_removed",
    "simple_invariant",
}
TRACKS = ("primary", "heldout", "decoy")


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def input_hashes(case_dir: Path) -> dict[str, str]:
    names = ("correct.v", "buggy.v", "tb.v", "tb_holdout.v", "golden.sva", "weak_assertions.sva", "weak_assertions.json")
    return {name: hashlib.sha256((case_dir / name).read_bytes()).hexdigest() for name in names}


def track_ok(result: dict, *, must_catch: bool) -> bool:
    if not result.get("compile_ok", False):
        return False
    if not result.get("good_pass", False):
        return False
    if not result.get("antecedent_hit_good", False):
        return False
    if not result.get("antecedent_hit_bad", False):
        return False
    if not result.get("non_vacuous_bad", False):
        return False
    return bool(result.get("bad_fail", False)) is must_catch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("rtl_cases_real_scale210_independent"))
    parser.add_argument("--min-weak-misses", type=int, default=2)
    args = parser.parse_args()
    root = args.root.resolve()
    inventory = root / "candidate_inventory_pre_final.json"
    cases = load(inventory if inventory.is_file() else root / "independent_new_bug_manifest.json")["cases"]
    rows = []
    admitted, rejected, pending = [], [], []

    for case in cases:
        case_dir = root / case["name"]
        evaluation_path = case_dir / "hardness_evaluation.json"
        row = {
            "case_name": case["name"],
            "parent_bug_id": case["parent_bug_id"],
            "bug_class": case["bug_class"],
            "evaluation_present": evaluation_path.is_file(),
            "golden_gate_ok": False,
            "weak_assertion_count": 0,
            "weak_kind_count": 0,
            "nonvacuous_weak_miss_count": 0,
            "hardness_ok": False,
            "decision": "pending",
            "reason": "missing hardness_evaluation.json",
        }
        if not evaluation_path.is_file():
            pending.append(case["name"])
            rows.append(row)
            continue

        evaluation = load(evaluation_path)
        evaluated_items = [evaluation.get("golden", {}), *evaluation.get("weak_assertions", [])]
        combinational_sampling = any(
            str(item.get("parsed", {}).get("event", "")) == "*"
            or not re.search(r"\b(?:posedge|negedge)\b", str(item.get("parsed", {}).get("event", "")))
            for item in evaluation.get("monitor_definitions", [])
        )
        revision_ok = int(evaluation.get("evaluator_revision", 0)) >= 5
        hashes_ok = evaluation.get("input_hashes") == input_hashes(case_dir)
        raw_metrics_complete = all(
            item.get(track, {}).get("good_failure_count") is not None
            and item.get(track, {}).get("bad_failure_count") is not None
            for item in evaluated_items for track in TRACKS
        )
        if not evaluation.get("evaluation_complete", False) or not raw_metrics_complete or not revision_ok or not hashes_ok:
            row["reason"] = "procedural monitor evaluation incomplete or unsupported"
            pending.append(case["name"])
            rows.append(row)
            continue
        golden = evaluation.get("golden", {})
        golden_gate_ok = all(track_ok(golden.get(track, {}), must_catch=True) for track in TRACKS)
        weak = evaluation.get("weak_assertions", [])
        kinds = {item.get("kind") for item in weak if item.get("kind")}
        weak_misses = []
        for item in weak:
            # A useful weak miss must be executable, pass the correct RTL, have
            # a real antecedent hit, and still miss all three buggy tracks. Vacuous
            # or uncompilable assertions never count as hardness evidence.
            if (
                item.get("declared_nonempty_antecedent", False)
                and all(track_ok(item.get(track, {}), must_catch=False) for track in TRACKS)
            ):
                weak_misses.append(item.get("name", "unnamed"))

        row.update(
            {
                "golden_gate_ok": golden_gate_ok,
                "weak_assertion_count": len(weak),
                "weak_kind_count": len(kinds & REQUIRED_WEAK_KINDS),
                "nonvacuous_weak_miss_count": len(weak_misses),
            }
        )
        schema_ok = len(weak) >= 5 and len(kinds & REQUIRED_WEAK_KINDS) == len(REQUIRED_WEAK_KINDS)
        row["hardness_ok"] = golden_gate_ok and schema_ok and len(weak_misses) >= args.min_weak_misses
        if row["hardness_ok"]:
            row["decision"] = "admitted"
            row["reason"] = f"golden catches all three tracks; weak misses={';'.join(weak_misses)}"
            admitted.append(case["name"])
        else:
            row["decision"] = "rejected"
            reasons = []
            if not golden_gate_ok:
                reasons.append("golden gate failed")
            if not schema_ok:
                reasons.append("need >=5 weak assertions spanning all 5 required kinds")
            if len(weak_misses) < args.min_weak_misses:
                reasons.append(f"nonvacuous weak misses {len(weak_misses)} < {args.min_weak_misses}")
            row["reason"] = "; ".join(reasons)
            rejected.append(case["name"])
        rows.append(row)

    report = root / "hardness_admission_report.csv"
    with report.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    decisions = root / "hardness_decisions"
    decisions.mkdir(exist_ok=True)
    for name, values in [("admitted_cases", admitted), ("rejected_cases", rejected), ("pending_cases", pending)]:
        (decisions / f"{name}.json").write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    summary = {
        "candidate_case_count": len(cases),
        "admitted_case_count": len(admitted),
        "rejected_case_count": len(rejected),
        "pending_case_count": len(pending),
        "minimum_nonvacuous_weak_misses": args.min_weak_misses,
        "required_weak_kinds": sorted(REQUIRED_WEAK_KINDS),
        "admission_rule": "complete procedural evaluation; golden catches primary+heldout+decoy; all 5 weak kinds; >=2 explicitly nonempty, nonvacuous weak assertions miss all three buggy tracks",
    }
    (root / "hardness_admission_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
