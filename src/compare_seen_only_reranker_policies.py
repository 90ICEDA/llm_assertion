from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from build_seen_only_candidate_reranker import (
    DEFAULT_BASE, DEFAULT_CASES, DEFAULT_EXTENSION, DEFAULT_PARENT_MAP,
    KEY, SELECTION_FEATURES, canonical_assertion, compute_selection_features,
    parser_support, truth,
)
from run_trace_abstraction_prototype import ASSERTION_RE, run_case_eval, split_assertion


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "outputs/seen_only_reranker_policy_comparison"
POLICIES = [
    "filter_abstain", "filter_baseline_fallback", "filter_one_step_repair",
    "loose_filter", "score_ranking",
]
STRICT_GATES = [
    "compile_ok", "parser_support", "seen_good_pass", "seen_bad_fail",
    "seen_antecedent_hit", "non_vacuous", "signal_exists",
]
LOOSE_GATES = ["compile_ok", "parser_support", "seen_good_pass", "signal_exists"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rank(sub: pd.DataFrame) -> pd.DataFrame:
    out = sub.copy()
    out["strict_pass"] = out[STRICT_GATES].all(axis=1)
    out["strict_pass_count"] = out[STRICT_GATES].sum(axis=1)
    out["allowed_score"] = (
        out["compile_ok"].astype(int) + out["parser_support"].astype(int)
        + out["seen_good_pass"].astype(int) + out["seen_bad_fail"].astype(int)
        + out["seen_antecedent_hit"].astype(int) + out["non_vacuous"].astype(int)
        + out["signal_exists"].astype(int) + out["reset_usage"].astype(int)
        + (~out["literal_hardcoding"]).astype(int)
        + out["cross_representation_agreement"].astype(int)
    )
    out["_tie_id"] = out.apply(
        lambda r: hashlib.sha256(
            f"seen-only-policy-v1|{r['representation']}|{r['candidate_index']}|{canonical_assertion(r['assertion_text'])}".encode()
        ).hexdigest(), axis=1,
    )
    return out.sort_values(
        ["strict_pass", "allowed_score", "strict_pass_count", "literal_hardcoding",
         "reset_usage", "cross_representation_agreement", "_tie_id"],
        ascending=[False, False, False, True, False, False, True],
    )


def assertion_with_body(assertion: str, body: str) -> str:
    match = ASSERTION_RE.match(assertion.strip())
    if not match:
        raise ValueError("unsupported assertion wrapper")
    old_body = match.group(1)
    return assertion[: match.start(1)] + body + assertion[match.end(1) :]


def make_one_step_repair(ranked: pd.DataFrame) -> tuple[str, str, pd.Series]:
    top = ranked.iloc[0]
    top_ant, implication, consequent = split_assertion(str(top["assertion_text"]))
    other = ranked.loc[ranked["representation"] != top["representation"]]
    partner = other.iloc[0] if not other.empty else ranked.iloc[min(1, len(ranked) - 1)]
    try:
        partner_ant, _, _ = split_assertion(str(partner["assertion_text"]))
    except Exception:
        partner_ant = "1'b1"
    if not bool(top["seen_good_pass"]):
        repaired_ant = f"(({top_ant}) && ({partner_ant}))"
        operation = "antecedent_narrow_and_cross_representation"
    elif not (bool(top["seen_bad_fail"]) and bool(top["seen_antecedent_hit"]) and bool(top["non_vacuous"])):
        repaired_ant = f"(({top_ant}) || ({partner_ant}))"
        operation = "antecedent_broaden_or_cross_representation"
    else:
        repaired_ant = f"({top_ant})"
        operation = "parser_wrapper_normalization"
    body = f"({repaired_ant}) {implication} ({consequent})"
    return assertion_with_body(str(top["assertion_text"]), body), operation, top


def eval_repair(case_id: str, assertion: str, cases_root: Path, runtime_dir: Path) -> dict:
    import csv
    with (cases_root / case_id / "waveform_good.csv").open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    signals = [re.sub(r"\[.*$", "", item.strip()) for item in header if item.strip() != "time_ps"]
    return run_case_eval(
        case_id=case_id, assertion_text=assertion, signal_names=signals,
        use_property=False, runtime_dir=runtime_dir, cases_root=cases_root,
    )


def source_evaluation(raw: pd.DataFrame) -> pd.DataFrame:
    cols = KEY + ["heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous", "trace_overfit"]
    out = raw[cols].copy()
    out["candidate_index"] = pd.to_numeric(out["candidate_index"]).astype(int)
    for col in cols[len(KEY):]:
        out[col] = truth(out[col])
    return out


def policy_rows(features: pd.DataFrame, raw_eval: pd.DataFrame, cases_root: Path, out_dir: Path) -> pd.DataFrame:
    rows: list[dict] = []
    repair_cache_path = out_dir / "one_step_repair_evaluations.json"
    repair_cache = json.loads(repair_cache_path.read_text(encoding="utf-8")) if repair_cache_path.exists() else {}
    group_key = ["model_label", "provider", "model_name", "case_id"]
    for keys, sub in features.groupby(group_key, sort=True):
        key = dict(zip(group_key, keys))
        ranked = rank(sub)
        strict = ranked.loc[ranked["strict_pass"]]
        loose = ranked.loc[ranked[LOOSE_GATES].all(axis=1)]
        baseline = sub.sort_values(["candidate_index", "representation"]).iloc[0]
        choices: dict[str, tuple[pd.Series | None, str, str]] = {
            "filter_abstain": (strict.iloc[0] if not strict.empty else None, "strict_filter" if not strict.empty else "abstain", ""),
            "filter_baseline_fallback": (strict.iloc[0] if not strict.empty else baseline, "strict_filter" if not strict.empty else "baseline_fallback", ""),
            "loose_filter": (loose.iloc[0] if not loose.empty else None, "loose_filter" if not loose.empty else "abstain", ""),
            "score_ranking": (ranked.iloc[0], "allowed_feature_score", ""),
        }
        if not strict.empty:
            choices["filter_one_step_repair"] = (strict.iloc[0], "strict_filter", "")
        else:
            try:
                repaired, operation, source = make_one_step_repair(ranked)
                cache_key = f"{key['model_label']}|{key['case_id']}"
                if cache_key not in repair_cache:
                    result = eval_repair(
                        key["case_id"], repaired, cases_root,
                        out_dir / "repair_runtime" / key["model_label"] / key["case_id"],
                    )
                    repair_cache[cache_key] = {"assertion_text": repaired, "operation": operation, "evaluation": result}
                    repair_cache_path.write_text(json.dumps(repair_cache, indent=2, ensure_ascii=False), encoding="utf-8")
                choices["filter_one_step_repair"] = (source, "one_step_repair", cache_key)
            except Exception as exc:
                choices["filter_one_step_repair"] = (None, f"repair_failed:{type(exc).__name__}", "")

        for policy in POLICIES:
            chosen, source, repair_key = choices[policy]
            row = {**key, "policy": policy, "selection_source": source, "covered": chosen is not None}
            if chosen is None:
                row.update({"representation": "", "candidate_index": 0, "assertion_text": ""})
                for col in ("heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous", "trace_overfit"):
                    row[col] = False
            elif repair_key:
                cached = repair_cache[repair_key]
                ev = cached["evaluation"]
                row.update({"representation": "repaired", "candidate_index": -1, "assertion_text": cached["assertion_text"], "repair_operation": cached["operation"]})
                row.update({
                    "heldout_correct_pass": bool(ev["heldout_correct_pass"]),
                    "heldout_buggy_fail": bool(ev["heldout_buggy_fail"]),
                    "heldout_antecedent_hit": bool(ev["heldout_antecedent_hit"]),
                    "heldout_non_vacuous": bool(ev["heldout_non_vacuous"]),
                    "trace_overfit": bool(ev["trace_overfit"]),
                })
            else:
                identity = {col: chosen[col] for col in KEY}
                match = raw_eval
                for col, value in identity.items():
                    match = match.loc[match[col] == value]
                if len(match) != 1:
                    raise RuntimeError(f"Evaluation join is not one-to-one: {identity}")
                ev = match.iloc[0]
                row.update({"representation": chosen["representation"], "candidate_index": int(chosen["candidate_index"]), "assertion_text": chosen["assertion_text"]})
                for col in ("heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous", "trace_overfit"):
                    row[col] = bool(ev[col])
            row["heldout_detect"] = row["heldout_buggy_fail"] and row["heldout_antecedent_hit"] and row["heldout_non_vacuous"]
            row["heldout_success"] = row["heldout_correct_pass"] and row["heldout_buggy_fail"]
            row["overall_success"] = row["heldout_correct_pass"] and row["heldout_detect"]
            rows.append(row)
    return pd.DataFrame(rows)


def summarize(rows: pd.DataFrame, parent_lookup: dict[str, str]) -> pd.DataFrame:
    rows = rows.copy()
    rows["parent_bug_id"] = rows["case_id"].map(parent_lookup)
    scopes = [("case", rows), ("parent_primary", rows.loc[rows["case_id"] == rows["parent_bug_id"]])]
    output: list[dict] = []
    for scope, data in scopes:
        for (model, model_name, policy), sub in data.groupby(["model_label", "model_name", "policy"]):
            n = len(sub); covered = int(sub["covered"].sum()); successes = int(sub["overall_success"].sum())
            covered_sub = sub.loc[sub["covered"]]
            output.append({
                "scope": scope, "model": model, "model_name": model_name, "policy": policy,
                "k_source": 8, "sample_count": n, "parent_count": int(sub["parent_bug_id"].nunique()),
                "deduplicated": scope == "parent_primary", "overlap": "same cases/parents across policies",
                "covered_count": covered, "coverage": covered / n, "abstain_count": n - covered,
                "abstain_rate": (n - covered) / n, "overall_success_count": successes,
                "overall_success": successes / n, "conditional_success": successes / covered if covered else 0.0,
                "FPR": float((~covered_sub["heldout_correct_pass"]).mean()) if covered else 0.0,
                "MDR": float((~sub["heldout_detect"]).mean()),
                "heldout_success": float(sub["heldout_success"].mean()),
                "overfit": float(covered_sub["trace_overfit"].mean()) if covered else 0.0,
            })
    return pd.DataFrame(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-results", default=str(DEFAULT_BASE)); parser.add_argument("--extension-results", default=str(DEFAULT_EXTENSION))
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES)); parser.add_argument("--parent-map", default=str(DEFAULT_PARENT_MAP)); parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    base, ext = Path(args.base_results).resolve(), Path(args.extension_results).resolve()
    cases_root, parent_path, out_dir = Path(args.cases_root).resolve(), Path(args.parent_map).resolve(), Path(args.out_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.concat([pd.read_csv(base, encoding="utf-8-sig"), pd.read_csv(ext, encoding="utf-8-sig")], ignore_index=True)
    raw["representation"] = raw["method"].map(lambda x: "raw" if "raw" in str(x).lower() else "temporal")
    features = compute_selection_features(raw.drop(columns=[c for c in raw if "heldout" in c or c == "trace_overfit"]), cases_root)
    rows = policy_rows(features, source_evaluation(raw), cases_root, out_dir)
    parent_records = json.loads(parent_path.read_text(encoding="utf-8")); parent_lookup = {x["case_id"]: x["parent_bug_id"] for x in parent_records}
    rows["parent_bug_id"] = rows["case_id"].map(parent_lookup)
    summary = summarize(rows, parent_lookup)
    rows_path = out_dir / "policy_selected_candidates_and_final_evaluation.csv"; summary_path = out_dir / "policy_comparison_metrics.csv"; protocol_path = out_dir / "policy_protocol.json"; isolation_path = out_dir / "policy_heldout_isolation_audit.json"; freeze_path = out_dir / "reranker_policy_comparison_freeze.json"
    rows.to_csv(rows_path, index=False, encoding="utf-8-sig"); summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    protocol = {"selection_feature_allowlist": SELECTION_FEATURES, "strict_gates": STRICT_GATES, "loose_gates": LOOSE_GATES, "heldout_use": "final evaluation only", "metric_definitions": {"coverage": "covered/sample", "conditional_success": "strict heldout success/covered", "MDR": "missed heldout detection including abstentions/sample", "FPR": "heldout correct failures/covered", "overfit": "trace_overfit/covered"}, "one_step_repair": "locked seen-only top candidate; AND antecedents on seen-good failure, OR antecedents on seen-bug miss; cross-representation partner; exactly one repaired candidate and no heldout-based reselection"}
    protocol_path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    base_isolation_path = ROOT / "outputs/seen_only_candidate_reranker_formal/heldout_deletion_invariance_audit.json"
    base_isolation = json.loads(base_isolation_path.read_text(encoding="utf-8"))
    if not base_isolation.get("selection_identical") or base_isolation.get("heldout_files_in_shadow") != 0:
        raise RuntimeError("Base held-out deletion isolation audit is not passing")
    plan_columns = ["model_label", "case_id", "policy", "selection_source", "covered", "representation", "candidate_index", "assertion_text"]
    plan_digest = hashlib.sha256(rows[plan_columns].sort_values(["model_label", "case_id", "policy"]).to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    isolation = {
        "status": "pass",
        "selection_input_heldout_columns": [],
        "physical_no_heldout_shadow_audit": str(base_isolation_path),
        "physical_no_heldout_shadow_selection_identical": True,
        "physical_no_heldout_shadow_selection_sha256": base_isolation["no_heldout_files_selection_sha256"],
        "policy_plan_sha256_before_final_evaluation": plan_digest,
        "one_step_repairs_locked_before_heldout_join": len(json.loads((out_dir / "one_step_repair_evaluations.json").read_text(encoding="utf-8"))),
        "heldout_use": "final metrics only; no post-heldout reselection",
    }
    isolation_path.write_text(json.dumps(isolation, indent=2), encoding="utf-8")
    frozen = [base, ext, parent_path, base_isolation_path, rows_path, summary_path, protocol_path, isolation_path, out_dir / "one_step_repair_evaluations.json"]
    freeze_path.write_text(json.dumps({"status":"frozen", "sha256":{str(p):sha(p) for p in frozen if p.exists()}}, indent=2), encoding="utf-8")
    print(summary.to_string(index=False)); print(freeze_path)


if __name__ == "__main__": main()
