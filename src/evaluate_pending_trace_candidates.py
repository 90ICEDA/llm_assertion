from __future__ import annotations

import argparse
import csv
from pathlib import Path

from run_multi_model_small_eval import (
    build_case_bundles, classify_failure, heuristic_semantic_reason,
    literal_hardcoding_flag, probe_property_support, run_case_eval,
)


ROOT = Path(__file__).resolve().parents[1]
KEYS = ("model_label", "case_id", "method", "candidate_index")


def truth(value: str) -> bool:
    return str(value).strip().lower() == "true"


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume WSL evaluation for generate-only trace candidates.")
    parser.add_argument("--root", default=str(ROOT / "rtl_cases_real_scale120"))
    parser.add_argument("--experiment-dir", required=True)
    parser.add_argument("--max-candidates", type=int, default=0)
    args = parser.parse_args()
    cases_root, experiment_dir = Path(args.root).resolve(), Path(args.experiment_dir).resolve()
    pending_path, results_path = experiment_dir / "pending_candidates.csv", experiment_dir / "multi_model_results_raw.csv"
    with pending_path.open(encoding="utf-8-sig", newline="") as handle: pending = list(csv.DictReader(handle))
    existing = []
    if results_path.exists():
        with results_path.open(encoding="utf-8-sig", newline="") as handle: existing = list(csv.DictReader(handle))
    result_by_key = {tuple(row[key] for key in KEYS): row for row in existing}
    remaining = [row for row in pending if tuple(row[key] for key in KEYS) not in result_by_key]
    if args.max_candidates: remaining = remaining[:args.max_candidates]
    if not remaining:
        print("No pending candidates remain."); return
    case_ids = sorted({row["case_id"] for row in remaining})
    bundles = {row["case_id"]: row for row in build_case_bundles(cases_root=cases_root, case_ids=case_ids)}
    use_property = probe_property_support(case_ids[0], cases_root=cases_root, runtime_dir=experiment_dir / "_probe")
    for index, pending_row in enumerate(remaining, 1):
        case_id, assertion_text = pending_row["case_id"], pending_row["assertion_text"]
        runtime_dir = experiment_dir / "runtime" / pending_row["model_label"] / case_id / pending_row["method"] / f"cand_{int(pending_row['candidate_index']):02d}"
        evaluated = run_case_eval(case_id=case_id, assertion_text=assertion_text, signal_names=bundles[case_id]["allowed_signals"], use_property=use_property, runtime_dir=runtime_dir, cases_root=cases_root)
        semantic_reasonable, semantic_reason = heuristic_semantic_reason(assertion_text)
        row = {key: pending_row.get(key, "") for key in pending_row if key != "evaluation_status"}
        row.update({
            "compile_ok": bool(evaluated["compile_ok"]), "correct_pass": bool(evaluated["correct_pass"]),
            "buggy_fail": bool(evaluated["buggy_fail"]), "antecedent_hit_buggy": bool(evaluated["antecedent_hit"]),
            "non_vacuous_buggy": bool(evaluated["non_vacuous"]), "heldout_correct_pass": bool(evaluated["heldout_correct_pass"]),
            "heldout_buggy_fail": bool(evaluated["heldout_buggy_fail"]), "heldout_antecedent_hit": bool(evaluated["heldout_antecedent_hit"]),
            "heldout_non_vacuous": bool(evaluated["heldout_non_vacuous"]), "trace_overfit": bool(evaluated["trace_overfit"]),
            "literal_hardcoding": literal_hardcoding_flag(assertion_text), "semantic_reasonable": semantic_reasonable,
            "semantic_reason": semantic_reason, "seen_good_ant_hits": int(evaluated["seen_good_ant_hits"]),
            "seen_bad_ant_hits": int(evaluated["seen_bad_ant_hits"]), "heldout_bad_ant_hits": int(evaluated["heldout_bad_ant_hits"]),
            "seen_good_fail_hits": int(evaluated["seen_good_fail_hits"]), "seen_bad_fail_hits": int(evaluated["seen_bad_fail_hits"]),
            "heldout_good_fail_hits": int(evaluated["heldout_good_fail_hits"]), "heldout_bad_fail_hits": int(evaluated["heldout_bad_fail_hits"]),
            "use_property_compile_mode": use_property,
        })
        failure_mode, failure_reason = classify_failure(row); row["failure_mode"] = failure_mode; row["failure_reason"] = failure_reason
        result_by_key[tuple(str(row[key]) for key in KEYS)] = row
        rows = list(result_by_key.values())
        with results_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        print(f"[{index}/{len(remaining)}] {pending_row['model_label']} {case_id} {pending_row['method']} c{pending_row['candidate_index']} -> {failure_mode}")


if __name__ == "__main__": main()
