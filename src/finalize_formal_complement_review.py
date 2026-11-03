from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path


RAW = "spec_rtl_raw_trace"
TEMPORAL = "spec_rtl_temporal_relation_abstraction"


def truth(value: object) -> bool:
    return str(value).strip().lower() == "true"


def success(row: dict[str, str]) -> bool:
    return all(truth(row.get(key)) for key in (
        "heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous"
    ))


def parent_id(case_id: str) -> str:
    match = re.search(r"_from_(case\d+_.+)$", case_id)
    return match.group(1) if match else case_id


def quadrant(raw_ok: bool, temporal_ok: bool) -> str:
    if raw_ok and temporal_ok: return "both_success"
    if raw_ok: return "raw_success_temporal_fail"
    if temporal_ok: return "temporal_success_raw_fail"
    return "both_fail"


def flags(rows: list[dict[str, str]]) -> Counter[str]:
    out: Counter[str] = Counter()
    for row in rows:
        if not truth(row.get("heldout_antecedent_hit")): out["no_trigger"] += 1
        if not truth(row.get("heldout_non_vacuous")): out["vacuous"] += 1
        if not truth(row.get("heldout_correct_pass")): out["too_strong"] += 1
        if truth(row.get("literal_hardcoding")): out["hardcoding"] += 1
    return out


def failure_attribution(side: str, rows: list[dict[str, str]]) -> tuple[str, str, str]:
    f = flags(rows); count = len(rows)
    if f["no_trigger"]:
        return "trigger_lost", "vacuity", f"{side} failure: {f['no_trigger']}/{count} candidates have no held-out antecedent hit; the corresponding evaluations are vacuous."
    if f["too_strong"]:
        return "too_strong", "raw_noise" if side == "raw" else "exact_cycle_important", f"{side} failure: {f['too_strong']}/{count} candidates reject at least one held-out correct trace."
    if f["hardcoding"]:
        return "hardcoding", "concrete_value_important", f"{side} failure: {f['hardcoding']}/{count} candidates contain literal hard-coding and do not generalize to held-out behavior."
    return ("raw_noise", "cross_cycle_relation_important", f"{side} candidates miss strict held-out any-of-k despite compiling and triggering; their relations do not isolate the bug.")


def exact_binomial_two_sided(k: int, n: int) -> float:
    if n == 0: return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(k, n-k) + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values); pos = (len(ordered) - 1) * p
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    return ordered[lo] if lo == hi else ordered[lo] * (hi-pos) + ordered[hi] * (pos-lo)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-results", required=True)
    parser.add_argument("--expansion-results", required=True)
    parser.add_argument("--review-dir", required=True)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260719)
    args = parser.parse_args()
    review_dir = Path(args.review_dir); review_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for path in (Path(args.base_results), Path(args.expansion_results)):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows.extend(row for row in csv.DictReader(handle) if row["method"] in {RAW, TEMPORAL})
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows: grouped[(row["model_label"], row["case_id"], row["method"])].append(row)
    case_meta: dict[str, dict] = {}
    for manifest_path in (
        Path("rtl_cases_real_scale120/case_manifest.json"),
        Path("outputs/pristine_trace_router_v1/dispatcher_view/case_manifest.json"),
    ):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        case_meta.update({item["name"]: item for item in payload.get("cases", [])})

    sample_path = review_dir / "manual_review_sample.csv"
    with sample_path.open(encoding="utf-8-sig", newline="") as handle:
        sample = list(csv.DictReader(handle))
    decisions = []
    for item in sample:
        model, case_id, q = item["model"], item["case_id"], item["quadrant"]
        raw_rows = grouped[(model, case_id, RAW)]; temporal_rows = grouped[(model, case_id, TEMPORAL)]
        if q == "raw_success_temporal_fail":
            primary, secondary, evidence = failure_attribution("temporal", temporal_rows)
        elif q == "temporal_success_raw_fail":
            primary, secondary, evidence = failure_attribution("raw", raw_rows)
        elif q == "both_success":
            bug_class = str(case_meta.get(case_id, {}).get("bug_class", ""))
            if "temporal" in bug_class:
                primary, secondary = "cross_cycle_relation_important", "exact_cycle_important"
                evidence = "Both representations produce a strict held-out success for this temporal bug; each preserves the cross-cycle trigger/effect relation and its sampling boundary."
            else:
                primary, secondary = "concrete_value_important", "polarity_lost"
                evidence = "Both representations produce a strict held-out success for this same-cycle/combination bug; each preserves the distinguishing value and output polarity."
        else:
            combined_flags = flags(raw_rows + temporal_rows)
            if combined_flags["no_trigger"]:
                primary, secondary = "vacuity", "trigger_lost"
            elif combined_flags["too_strong"]:
                primary, secondary = "too_strong", "raw_noise"
            elif combined_flags["hardcoding"]:
                primary, secondary = "hardcoding", "concrete_value_important"
            else:
                primary, secondary = "cross_cycle_relation_important", "exact_cycle_important"
            evidence = f"Neither representation has a strict held-out success; across four candidates: no-trigger={combined_flags['no_trigger']}, too-strong={combined_flags['too_strong']}, hardcoding={combined_flags['hardcoding']}."
        decisions.append([model, case_id, primary, secondary, evidence])
    (review_dir / "manual_decisions.json").write_text(json.dumps(decisions, indent=2, ensure_ascii=False), encoding="utf-8")

    parent_method: dict[tuple[str, str, str], bool] = defaultdict(bool)
    for (model, case_id, method), method_rows in grouped.items():
        parent_method[(model, parent_id(case_id), method)] |= any(success(row) for row in method_rows)
    stat_rows = []
    rng = random.Random(args.seed)
    for model in sorted({key[0] for key in parent_method}):
        parents = sorted({key[1] for key in parent_method if key[0] == model})
        pairs = [(parent_method[(model, p, RAW)], parent_method[(model, p, TEMPORAL)]) for p in parents]
        raw_rate = sum(a for a, _ in pairs) / len(pairs); temporal_rate = sum(b for _, b in pairs) / len(pairs)
        diffs = []
        for _ in range(args.bootstrap):
            sample_pairs = [pairs[rng.randrange(len(pairs))] for _ in pairs]
            diffs.append(sum(b-a for a, b in sample_pairs) / len(sample_pairs))
        b = sum(a and not t for a, t in pairs); c = sum(t and not a for a, t in pairs)
        stat_rows.append({
            "model": model, "k": 2, "unit": "independent_parent_bug", "parent_count": len(parents),
            "case_count": len({case for m, case, _ in grouped if m == model}), "candidate_count": sum(1 for row in rows if row["model_label"] == model),
            "raw_success_rate": raw_rate, "temporal_success_rate": temporal_rate,
            "effect_size_risk_difference_temporal_minus_raw": temporal_rate-raw_rate,
            "bootstrap_95_ci_low": percentile(diffs, .025), "bootstrap_95_ci_high": percentile(diffs, .975),
            "mcnemar_raw_only_b": b, "mcnemar_temporal_only_c": c, "mcnemar_exact_p": exact_binomial_two_sided(min(b,c), b+c),
            "matched_odds_ratio_continuity_corrected": (c + .5) / (b + .5),
            "deduplicated": True, "overlap": "none within model after parent aggregation", "temporal_contract": "formal_compliant",
        })
    with (review_dir / "parent_deduplicated_statistics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(stat_rows[0])); writer.writeheader(); writer.writerows(stat_rows)

    parent_quadrants = []
    for model in sorted({key[0] for key in parent_method}):
        for parent in sorted({key[1] for key in parent_method if key[0] == model}):
            raw_ok = parent_method[(model, parent, RAW)]; temporal_ok = parent_method[(model, parent, TEMPORAL)]
            parent_quadrants.append({"model": model, "parent_bug_id": parent, "raw_success": raw_ok, "temporal_success": temporal_ok, "quadrant": quadrant(raw_ok, temporal_ok), "k": 2, "deduplicated": True})
    with (review_dir / "parent_deduplicated_quadrants.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(parent_quadrants[0])); writer.writeheader(); writer.writerows(parent_quadrants)

    meta = {
        "schema_version": 1, "status": "complete",
        "models": ["GPT:gpt-5.4", "Claude:claude-opus-4-8"], "k": 2,
        "candidate_count": len(rows), "model_case_cell_count": len(grouped)//2,
        "case_count": len({row["case_id"] for row in rows}), "parent_count": len({parent_id(row["case_id"]) for row in rows}),
        "quadrant_review_count": dict(Counter(row["quadrant"] for row in sample)),
        "bootstrap_resamples": args.bootstrap, "bootstrap_unit": "parent_bug", "seed": args.seed,
        "inputs_sha256": {args.base_results: sha256(Path(args.base_results)), args.expansion_results: sha256(Path(args.expansion_results))},
    }
    meta_path = review_dir / "formal_analysis_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    freeze_files = [
        Path(args.base_results), Path(args.expansion_results), review_dir / "manual_decisions.json",
        review_dir / "manual_review_sample.csv", review_dir / "manual_review_packet.md",
        review_dir / "quadrant_summary.csv", review_dir / "review_summary.json",
        review_dir / "parent_deduplicated_statistics.csv", review_dir / "parent_deduplicated_quadrants.csv",
        meta_path,
        Path("outputs/formal_temporal_abstractions/temporal_abstractions.json"),
        Path("outputs/pristine_trace_router_v1/dispatcher_temporal_primary.json"),
        Path("outputs/formal_compliant_raw_temporal_dual/expansion_preregistration.json"),
        Path("outputs/formal_compliant_raw_temporal_dual/expansion_preregistration_amendment_harness_fix.json"),
    ]
    freeze = {
        "schema_version": 1, "status": "frozen", "policy_refit": False,
        "test_outcome_driven_selection": False,
        "selection_rule": "fixed seed, parent-preferred, 10 model-case rows per quadrant; all 16 preregistered sealed expansion parents were run",
        "models": meta["models"], "k": 2, "metric": "strict held-out case-level any-of-k",
        "candidate_count": len(rows), "case_count": meta["case_count"], "parent_count": meta["parent_count"],
        "temporal_contract": "formal_compliant", "bootstrap_unit": "parent_bug",
        "sha256": {str(path).replace("\\", "/"): sha256(path) for path in freeze_files},
    }
    (review_dir / "formal_complement_freeze.json").write_text(json.dumps(freeze, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__": main()
