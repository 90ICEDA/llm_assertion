#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from build_seen_only_candidate_reranker import (
    canonical_assertion, referenced_signals, signal_inventory, truth,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/formal_compliant_raw_temporal_dual/multi_model_results_raw.csv"
EXT = ROOT / "outputs/candidate_portfolio_k4_extension/multi_model_results_raw.csv"
FOUR = ROOT / "outputs/formal_compliant_four_trace_dual/multi_model_results_raw.csv"
PARENT_MAP = ROOT / "outputs/formal_four_trace_representations/trace_representations.json"
CASES = ROOT / "rtl_cases_real_scale120"
OUT = ROOT / "deliverables/equal_budget_visible_selection_20260809"

REP_MAP = {
    "spec_rtl_raw_trace": "raw",
    "spec_rtl_naive_summary": "naive",
    "spec_rtl_event_abstraction": "event",
    "spec_rtl_temporal_relation_abstraction": "temporal",
}
POOL_ORDER = ["raw_k4", "temporal_k4", "raw2_temporal2", "four_rep_one_each"]
VISIBLE_POLICIES = ["first", "random", "hard_filter", "score_ranking", "abstain", "fallback"]
ALL_POLICIES = VISIBLE_POLICIES + ["oracle_upper_bound"]
VISIBLE_FEATURES = [
    "compile_ok", "seen_good_pass", "seen_bad_fail", "seen_antecedent_hit",
    "non_vacuous", "signal_legal", "reset_valid", "no_hardcoding",
    "representation_agreement",
]
HARD_GATES = [
    "compile_ok", "seen_good_pass", "seen_bad_fail", "seen_antecedent_hit",
    "non_vacuous", "signal_legal", "reset_valid", "no_hardcoding",
]
HELDOUT_COLUMNS = [
    "heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit",
    "heldout_non_vacuous", "trace_overfit", "heldout_bad_ant_hits",
    "heldout_good_fail_hits", "heldout_bad_fail_hits",
]


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def candidate_uid(row: pd.Series) -> str:
    return f"{row['source']}|{row['method']}|c{int(row['candidate_index'])}"


def load_sources() -> tuple[pd.DataFrame, dict[str, str]]:
    frames = []
    for source, path in [("base", BASE), ("extension", EXT), ("four_rep", FOUR)]:
        frame = pd.read_csv(path, encoding="utf-8-sig")
        frame["source"] = source
        frame["representation"] = frame["method"].map(REP_MAP)
        if frame["representation"].isna().any():
            raise RuntimeError(f"Unknown representation in {path}")
        frame["candidate_index"] = pd.to_numeric(frame["candidate_index"], errors="raise").astype(int)
        frames.append(frame)
    parent_records = json.loads(PARENT_MAP.read_text(encoding="utf-8"))
    parent_lookup = {str(x["case_id"]): str(x["parent_bug_id"]) for x in parent_records}
    return pd.concat(frames, ignore_index=True), parent_lookup


def build_pools(raw: pd.DataFrame, parent_lookup: dict[str, str]) -> pd.DataFrame:
    b = raw.loc[raw.source == "base"]
    e = raw.loc[raw.source == "extension"]
    f = raw.loc[raw.source == "four_rep"]
    pieces = []
    definitions = {
        "raw_k4": pd.concat([b.loc[b.representation == "raw"], e.loc[e.representation == "raw"]]),
        "temporal_k4": pd.concat([b.loc[b.representation == "temporal"], e.loc[e.representation == "temporal"]]),
        "raw2_temporal2": b.loc[b.representation.isin(["raw", "temporal"])],
        "four_rep_one_each": f.loc[f.candidate_index == 1],
    }
    for pool_name, frame in definitions.items():
        part = frame.copy()
        part["pool"] = pool_name
        pieces.append(part)
    pools = pd.concat(pieces, ignore_index=True)
    pools["parent_bug_id"] = pools.case_id.map(parent_lookup)
    if pools.parent_bug_id.isna().any():
        raise RuntimeError("Missing parent mapping")
    pools["candidate_uid"] = pools.apply(candidate_uid, axis=1)
    slot_order = {rep: i for i, rep in enumerate(["raw", "temporal", "naive", "event"], start=1)}
    pools["_rep_order"] = pools.representation.map(slot_order)
    pools = pools.sort_values(["pool", "model_label", "case_id", "_rep_order", "candidate_index", "source"])
    pools["pool_slot"] = pools.groupby(["pool", "model_label", "case_id"]).cumcount() + 1
    counts = pools.groupby(["pool", "model_label", "case_id"]).size()
    if len(counts) != 4 * 2 * 120 or not counts.eq(4).all():
        raise RuntimeError(f"Equal-budget pool failure: {counts.value_counts().to_dict()}")
    if pools.duplicated(["pool", "model_label", "case_id", "candidate_uid"]).any():
        raise RuntimeError("Duplicate candidate identity inside pool")
    return pools.drop(columns=["_rep_order"])


def compute_visible_features(pools: pd.DataFrame) -> pd.DataFrame:
    required = {
        "compile_ok", "correct_pass", "buggy_fail", "antecedent_hit_buggy",
        "non_vacuous_buggy", "literal_hardcoding", "assertion_text",
    }
    if missing := sorted(required - set(pools.columns)):
        raise RuntimeError(f"Missing visible source fields: {missing}")
    out = pools.copy()
    out["compile_ok"] = truth(out.compile_ok)
    out["seen_good_pass"] = truth(out.correct_pass)
    out["seen_bad_fail"] = truth(out.buggy_fail)
    out["seen_antecedent_hit"] = truth(out.antecedent_hit_buggy)
    out["non_vacuous"] = truth(out.non_vacuous_buggy)
    out["no_hardcoding"] = ~truth(out.literal_hardcoding)
    inventories = {case: signal_inventory(CASES / case) for case in out.case_id.unique()}
    legal, reset_valid = [], []
    for row in out.itertuples(index=False):
        signals, resets = inventories[row.case_id]
        refs = referenced_signals(str(row.assertion_text))
        legal.append(bool(refs) and refs.issubset(signals))
        lower = str(row.assertion_text).lower()
        combinational = "@(*)" in lower or "@*" in lower
        reset_valid.append(
            combinational if not resets else (
                "disable iff" in lower
                and any(re.search(rf"\b{re.escape(reset.lower())}\b", lower) for reset in resets)
            )
        )
    out["signal_legal"] = legal
    out["reset_valid"] = reset_valid
    out["_canonical"] = out.assertion_text.map(canonical_assertion)
    agreement = out.groupby(
        ["pool", "model_label", "case_id", "_canonical"]
    ).representation.transform("nunique")
    out["representation_agreement"] = agreement.ge(2)
    out["hard_pass"] = out[HARD_GATES].all(axis=1)
    out["visible_score"] = out[VISIBLE_FEATURES].astype(int).sum(axis=1)
    out["visible_feature_vector"] = out[VISIBLE_FEATURES].astype(int).astype(str).agg("".join, axis=1)
    out["visible_tie_hash"] = out.apply(
        lambda r: digest_text(
            f"visible-selection-v2|{r['pool']}|{r['model_label']}|{r['case_id']}|{r['candidate_uid']}|{r['pool_slot']}"
        ), axis=1,
    )
    return out


def heldout_eval(row: pd.Series) -> dict[str, bool]:
    result = {col: bool(truth(pd.Series([row.get(col, False)])).iloc[0]) for col in HELDOUT_COLUMNS if col in row.index}
    for col in HELDOUT_COLUMNS:
        result.setdefault(col, False)
    result["heldout_strict_success"] = (
        result["heldout_correct_pass"] and result["heldout_buggy_fail"]
        and result["heldout_antecedent_hit"] and result["heldout_non_vacuous"]
    )
    return result


def visible_rank(sub: pd.DataFrame) -> pd.DataFrame:
    return sub.sort_values(
        ["visible_score", "hard_pass", "representation_agreement", "no_hardcoding", "reset_valid", "visible_tie_hash"],
        ascending=[False, False, False, False, False, True],
    )


def choose_visible(sub: pd.DataFrame, policy: str) -> tuple[pd.Series | None, str]:
    by_first = sub.sort_values("pool_slot")
    ranked = visible_rank(sub)
    strict_first = by_first.loc[by_first.hard_pass]
    strict_ranked = ranked.loc[ranked.hard_pass]
    if policy == "first":
        return (by_first.iloc[0], "first_pool_slot") if not strict_first.empty else (None, "abstain_no_hard_pass")
    if policy == "random":
        if strict_first.empty:
            return None, "abstain_no_hard_pass"
        keyed = by_first.copy()
        keyed["_random_hash"] = keyed.apply(
            lambda r: digest_text(f"equal-budget-random-v1|{r['model_label']}|{r['case_id']}|{r['pool']}|{r['candidate_uid']}"), axis=1
        )
        return keyed.sort_values("_random_hash").iloc[0], "deterministic_random"
    if policy == "hard_filter":
        return (strict_first.iloc[0], "hard_filter_first") if not strict_first.empty else (None, "abstain_no_hard_pass")
    if policy == "score_ranking":
        return (ranked.iloc[0], "visible_score_ranking") if not strict_ranked.empty else (None, "abstain_no_hard_pass")
    if policy == "abstain":
        return (strict_ranked.iloc[0], "hard_pass_score_ranking") if not strict_ranked.empty else (None, "abstain_no_hard_pass")
    if policy == "fallback":
        return (strict_ranked.iloc[0], "hard_pass_score_ranking") if not strict_ranked.empty else (by_first.iloc[0], "explicit_fallback_first")
    raise ValueError(policy)


def select_all(features: pd.DataFrame, include_oracle: bool = True) -> pd.DataFrame:
    rows = []
    group = ["pool", "model_label", "provider", "model_name", "case_id", "parent_bug_id"]
    for keys, sub in features.groupby(group, sort=True, dropna=False):
        key = dict(zip(group, keys))
        for policy in VISIBLE_POLICIES:
            chosen, source = choose_visible(sub, policy)
            record = selected_record(key, policy, chosen, source)
            record.update(zero_pass_audit_fields(sub, policy, chosen))
            rows.append(record)
        if include_oracle:
            oracle = sub.copy()
            oracle["_oracle_success"] = oracle.apply(lambda r: heldout_eval(r)["heldout_strict_success"], axis=1)
            successes = oracle.loc[oracle._oracle_success]
            chosen = successes.sort_values("pool_slot").iloc[0] if not successes.empty else None
            source = "oracle_success" if chosen is not None else "oracle_abstain_no_success"
            record = selected_record(key, "oracle_upper_bound", chosen, source)
            record.update(zero_pass_audit_fields(sub, "oracle_upper_bound", chosen))
            rows.append(record)
    return pd.DataFrame(rows)


def zero_pass_audit_fields(sub: pd.DataFrame, policy: str, chosen: pd.Series | None) -> dict:
    pool_has_hard_pass = bool(sub.hard_pass.any())
    if pool_has_hard_pass:
        disposition = "hard_pass_available"
    elif chosen is None:
        disposition = "explicit_abstain"
    elif policy == "fallback":
        disposition = "explicit_fallback"
    elif policy in {"first", "random", "score_ranking"}:
        disposition = "explicit_abstain"
    else:
        disposition = "oracle_evaluation_only"
    return {
        "pool_has_hard_pass": pool_has_hard_pass,
        "selected_candidate_hard_pass": bool(chosen is not None and chosen.hard_pass),
        "zero_pass_disposition": disposition,
        "implicit_fallback": False,
    }


def selected_record(key: dict, policy: str, chosen: pd.Series | None, source: str) -> dict:
    row = {**key, "policy": policy, "selection_source": source, "covered": chosen is not None, "abstained": chosen is None}
    if chosen is None:
        row.update({
            "pool_slot": 0, "candidate_uid": "", "representation": "", "candidate_index": 0,
            "assertion_text": "", "visible_score": 0, "hard_pass": False,
            "visible_feature_vector": "", "representation_agreement": False,
        })
        row.update({col: False for col in HELDOUT_COLUMNS})
        row["heldout_strict_success"] = False
        return row
    row.update({
        "pool_slot": int(chosen.pool_slot), "candidate_uid": chosen.candidate_uid,
        "representation": chosen.representation, "candidate_index": int(chosen.candidate_index),
        "assertion_text": chosen.assertion_text, "visible_score": int(chosen.visible_score),
        "hard_pass": bool(chosen.hard_pass), "visible_feature_vector": chosen.visible_feature_vector,
        "representation_agreement": bool(chosen.representation_agreement),
    })
    row.update(heldout_eval(chosen))
    return row


def selection_hash(selected: pd.DataFrame) -> str:
    cols = [
        "pool", "model_label", "case_id", "policy", "covered", "selection_source",
        "candidate_uid", "assertion_text", "pool_has_hard_pass",
        "selected_candidate_hard_pass", "zero_pass_disposition", "implicit_fallback",
    ]
    visible = selected.loc[selected.policy.isin(VISIBLE_POLICIES), cols].sort_values(cols[:4])
    return digest_text(visible.to_csv(index=False, lineterminator="\n"))


def summarize(selected: pd.DataFrame, canonical_cases: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail = selected.copy()
    scopes = {
        "case_all_variants": detail,
        "parent_primary": detail.loc[detail.case_id.isin(canonical_cases)],
    }
    summaries = []
    for scope, data in scopes.items():
        for (model, pool, policy), sub in data.groupby(["model_label", "pool", "policy"], sort=True):
            covered = int(sub.covered.sum()); success = int(sub.heldout_strict_success.sum()); n = len(sub)
            summaries.append({
                "scope": scope, "model": model, "pool": pool, "policy": policy,
                "budget": 4, "sample_count": n, "parent_count": int(sub.parent_bug_id.nunique()),
                "covered_count": covered, "coverage": covered / n, "abstain_count": n - covered,
                "overall_success_count": success, "overall_success_rate": success / n,
                "conditional_success_rate": success / covered if covered else 0.0,
                "selection_uses_heldout": policy == "oracle_upper_bound",
            })
    parent_primary = detail.loc[detail.case_id.isin(canonical_cases)].copy()
    if parent_primary.groupby(["pool", "model_label", "policy"]).size().ne(len(canonical_cases)).any():
        raise RuntimeError("Parent-primary deduplication is incomplete")
    return pd.DataFrame(summaries), parent_primary


def coverage_curve(features: pd.DataFrame, canonical_cases: set[str]) -> pd.DataFrame:
    rows = []
    primary = features.loc[features.case_id.isin(canonical_cases)]
    group = ["pool", "model_label", "provider", "model_name", "case_id", "parent_bug_id"]
    tops = []
    for _, sub in primary.groupby(group, sort=True):
        tops.append(visible_rank(sub).iloc[0])
    top = pd.DataFrame(tops)
    top["heldout_strict_success"] = top.apply(lambda r: heldout_eval(r)["heldout_strict_success"], axis=1)
    max_score = len(VISIBLE_FEATURES)
    for (pool, model), sub in top.groupby(["pool", "model_label"], sort=True):
        for threshold in range(max_score + 1):
            covered = sub.loc[sub.visible_score >= threshold]
            success = int(covered.heldout_strict_success.sum()); n = len(sub)
            rows.append({
                "scope": "parent_primary", "model": model, "pool": pool,
                "score_threshold": threshold, "sample_count": n,
                "covered_count": len(covered), "coverage": len(covered) / n,
                "success_count": success, "overall_success_rate": success / n,
                "conditional_success_rate": success / len(covered) if len(covered) else 0.0,
            })
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw, parent_lookup = load_sources()
    pools = build_pools(raw, parent_lookup)
    heldout_present = [c for c in HELDOUT_COLUMNS if c in pools.columns]
    visible_input = pools.drop(columns=heldout_present)
    features_visible = compute_visible_features(visible_input)
    eval_cols = ["pool", "model_label", "case_id", "candidate_uid"] + heldout_present
    evaluation = pools[eval_cols].copy()
    features = features_visible.merge(evaluation, on=["pool", "model_label", "case_id", "candidate_uid"], how="left", validate="one_to_one")
    selected = select_all(features)
    original_hash = selection_hash(selected)

    deleted_selected = select_all(compute_visible_features(pools.drop(columns=heldout_present)), include_oracle=False)
    deleted_hash = selection_hash(deleted_selected)
    shuffled = pools.copy()
    rng = np.random.default_rng(20260809)
    for col in heldout_present:
        shuffled[col] = rng.permutation(shuffled[col].to_numpy())
    shuffled_features = compute_visible_features(shuffled.drop(columns=heldout_present))
    shuffled_selected = select_all(shuffled_features, include_oracle=False)
    shuffled_hash = selection_hash(shuffled_selected)
    if not (original_hash == deleted_hash == shuffled_hash):
        raise RuntimeError("Held-out deletion/shuffle selection hash invariance failed")

    canonical_cases = {case for case, parent in parent_lookup.items() if case == parent}
    if len(canonical_cases) != 40:
        raise RuntimeError(f"Expected 40 canonical parents, found {len(canonical_cases)}")
    summary, parent_primary = summarize(selected, canonical_cases)
    curve = coverage_curve(features, canonical_cases)
    feature_export = features_visible.drop(columns=["_canonical"])
    feature_export.to_csv(OUT / "visible_only_candidate_features.csv", index=False, encoding="utf-8-sig")
    selected.to_csv(OUT / "selected_candidate_details.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUT / "equal_budget_comparison.csv", index=False, encoding="utf-8-sig")
    parent_primary.to_csv(OUT / "parent_deduplicated_results.csv", index=False, encoding="utf-8-sig")
    curve.to_csv(OUT / "coverage_success_curve.csv", index=False, encoding="utf-8-sig")
    pool_manifest = features.groupby(["pool", "model_label", "case_id"], as_index=False).agg(
        budget=("candidate_uid", "size"), distinct_candidates=("candidate_uid", "nunique"),
        representations=("representation", lambda x: ";".join(x)),
    )
    pool_manifest.to_csv(OUT / "equal_budget_pool_manifest.csv", index=False, encoding="utf-8-sig")
    audit = {
        "status": "pass", "schema_version": 1,
        "visible_policy_count": len(VISIBLE_POLICIES), "oracle_excluded_from_invariance_hash": True,
        "selection_feature_allowlist": VISIBLE_FEATURES,
        "hard_gate_allowlist": HARD_GATES,
        "forbidden_heldout_columns": heldout_present,
        "selection_join_timing": "held-out fields joined only after visible features and candidate pools are locked",
        "original_visible_selection_sha256": original_hash,
        "heldout_deleted_selection_sha256": deleted_hash,
        "heldout_shuffled_selection_sha256": shuffled_hash,
        "heldout_deletion_hash_identical": original_hash == deleted_hash,
        "heldout_shuffle_hash_identical": original_hash == shuffled_hash,
        "pool_budget_all_four": bool(pool_manifest.budget.eq(4).all()),
        "pool_distinct_candidates_all_four": bool(pool_manifest.distinct_candidates.eq(4).all()),
        "canonical_parent_count": len(canonical_cases),
        "case_count": len(parent_lookup), "models": sorted(features.model_label.unique()),
        "no_implicit_fallback": True,
        "zero_pass_behavior": {
            "hard_filter": "abstain_no_hard_pass", "abstain": "abstain_no_hard_pass",
            "fallback": "explicit_fallback_first", "repair": "not run in this experiment",
            "first_random_score_ranking": "explicit abstain when the pool has zero hard-pass candidates",
        },
    }
    (OUT / "heldout_invariance_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    protocol = {
        "candidate_budget": 4,
        "pools": {
            "raw_k4": "raw candidates 1-4",
            "temporal_k4": "temporal candidates 1-4",
            "raw2_temporal2": "raw candidates 1-2 plus temporal candidates 1-2",
            "four_rep_one_each": "candidate 1 from raw, naive summary, event abstraction, temporal abstraction",
        },
        "policies": {
            "first": "pool slot 1 when any hard-pass candidate exists; otherwise explicit abstain",
            "random": "deterministic SHA-256 random choice when any hard-pass exists; otherwise explicit abstain",
            "hard_filter": "first hard-pass candidate; otherwise explicit abstain",
            "score_ranking": "highest visible-only score when any hard-pass exists; otherwise explicit abstain",
            "abstain": "highest-scoring hard-pass candidate; otherwise explicit abstain",
            "fallback": "highest-scoring hard-pass candidate; otherwise explicit fallback to slot 1",
            "oracle_upper_bound": "first held-out strict-success candidate; evaluation ceiling only",
        },
        "visible_score": "unweighted sum of the nine allow-listed binary features",
        "heldout_strict_success": "heldout correct pass AND buggy fail AND antecedent hit AND non-vacuous",
        "primary_scope": "40 canonical parents where case_id == parent_bug_id",
    }
    (OUT / "selection_protocol.json").write_text(json.dumps(protocol, indent=2, ensure_ascii=False), encoding="utf-8")
    print(summary.loc[summary.scope.eq("parent_primary")].to_string(index=False))
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
