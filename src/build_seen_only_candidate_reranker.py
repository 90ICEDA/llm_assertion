from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from run_trace_abstraction_prototype import split_assertion


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "outputs/formal_compliant_raw_temporal_dual/multi_model_results_raw.csv"
DEFAULT_EXTENSION = ROOT / "outputs/candidate_portfolio_k4_extension/multi_model_results_raw.csv"
DEFAULT_CASES = ROOT / "rtl_cases_real_scale120"
DEFAULT_OUT = ROOT / "outputs/seen_only_candidate_reranker_formal"
DEFAULT_PARENT_MAP = ROOT / "outputs/formal_four_trace_representations/trace_representations.json"

HELDOUT_COLUMNS = {
    "heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit",
    "heldout_non_vacuous", "heldout_bad_ant_hits", "heldout_good_fail_hits",
    "heldout_bad_fail_hits", "trace_overfit",
}
SELECTION_FEATURES = [
    "compile_ok", "parser_support", "seen_good_pass", "seen_bad_fail",
    "seen_antecedent_hit", "non_vacuous", "signal_exists", "reset_usage",
    "literal_hardcoding", "cross_representation_agreement",
]
KEY = ["model_label", "provider", "model_name", "case_id", "representation", "candidate_index"]
SV_WORDS = {
    "assert", "property", "posedge", "negedge", "disable", "iff", "and", "or",
    "not", "throughout", "until", "until_with", "s_until", "s_until_with",
    "strong", "weak", "inside", "intersect", "first_match", "true", "false",
}


def truth(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.fillna("").astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_assertion(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def parser_support(text: str) -> bool:
    try:
        split_assertion(str(text or ""))
        return True
    except Exception:
        return False


def signal_inventory(case_dir: Path) -> tuple[set[str], set[str]]:
    signals: set[str] = set()
    waveform = case_dir / "waveform_good.csv"
    if waveform.exists():
        with waveform.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle), [])
        signals.update(re.sub(r"\[.*$", "", item.strip()) for item in header)
    correct = case_dir / "correct.v"
    if correct.exists():
        text = re.sub(r"//.*?$|/\*.*?\*/", " ", correct.read_text(encoding="utf-8", errors="replace"), flags=re.M | re.S)
        signals.update(re.findall(r"\b[A-Za-z_][A-Za-z0-9_$]*\b", text))
    resets = {name for name in signals if re.fullmatch(r"rst(?:_n|_ni)?|reset(?:_n|_ni)?", name, flags=re.I)}
    return signals, resets


def referenced_signals(assertion: str) -> set[str]:
    text = re.sub(r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+", " ", assertion)
    text = re.sub(r"\$[A-Za-z_][A-Za-z0-9_$]*", " ", text)
    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_$]*\b", text))
    return {t for t in tokens if t.lower() not in SV_WORDS and not t.startswith("$")}


def compute_selection_features(df: pd.DataFrame, cases_root: Path) -> pd.DataFrame:
    required = {
        "model_label", "provider", "model_name", "case_id", "method", "candidate_index",
        "assertion_text", "compile_ok", "correct_pass", "buggy_fail", "antecedent_hit_buggy",
        "non_vacuous_buggy", "literal_hardcoding",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Missing selection input columns: {missing}")
    out = df[list(required)].copy()
    out["representation"] = out["method"].map(
        lambda value: "raw" if "raw" in str(value).lower() else "temporal"
    )
    out["candidate_index"] = pd.to_numeric(out["candidate_index"], errors="raise").astype(int)
    out["compile_ok"] = truth(out["compile_ok"])
    out["parser_support"] = out["assertion_text"].map(parser_support)
    out["seen_good_pass"] = truth(out["correct_pass"])
    out["seen_bad_fail"] = truth(out["buggy_fail"])
    out["seen_antecedent_hit"] = truth(out["antecedent_hit_buggy"])
    out["non_vacuous"] = truth(out["non_vacuous_buggy"])
    out["literal_hardcoding"] = truth(out["literal_hardcoding"])

    inventories = {case: signal_inventory(cases_root / case) for case in out["case_id"].unique()}
    signal_exists: list[bool] = []
    reset_usage: list[bool] = []
    for row in out.itertuples(index=False):
        signals, resets = inventories[row.case_id]
        refs = referenced_signals(row.assertion_text)
        signal_exists.append(bool(refs) and refs.issubset(signals))
        assertion_lower = str(row.assertion_text).lower()
        combinational = "@(*)" in assertion_lower or "@*" in assertion_lower
        reset_usage.append(
            combinational if not resets else (
                "disable iff" in assertion_lower
                and any(re.search(rf"\b{re.escape(reset.lower())}\b", assertion_lower) for reset in resets)
            )
        )
    out["signal_exists"] = signal_exists
    out["reset_usage"] = reset_usage

    out["_canonical"] = out["assertion_text"].map(canonical_assertion)
    agreement = (
        out.groupby(["model_label", "provider", "model_name", "case_id", "_canonical"])["representation"]
        .transform("nunique")
    )
    out["cross_representation_agreement"] = (agreement >= 2)
    return out


def select_candidates(features: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.Series] = []
    group_key = ["model_label", "provider", "model_name", "case_id"]
    gate_cols = [
        "compile_ok", "parser_support", "seen_good_pass", "seen_bad_fail",
        "seen_antecedent_hit", "non_vacuous", "signal_exists",
    ]
    for _, sub in features.groupby(group_key, sort=True, dropna=False):
        ranked = sub.copy()
        ranked["all_seen_gates_pass"] = ranked[gate_cols].all(axis=1)
        ranked["seen_gate_pass_count"] = ranked[gate_cols].sum(axis=1)
        ranked["_tie_id"] = ranked.apply(
            lambda r: hashlib.sha256(
                f"seen-only-reranker-v1|{r['representation']}|{r['candidate_index']}|{canonical_assertion(r['assertion_text'])}".encode()
            ).hexdigest(), axis=1,
        )
        # Every ranked field is on the explicit allow-list. _tie_id only resolves
        # exact feature ties and carries no experimental outcome information.
        ranked = ranked.sort_values(
            ["all_seen_gates_pass", "seen_gate_pass_count", "literal_hardcoding",
             "reset_usage", "cross_representation_agreement", "_tie_id"],
            ascending=[False, False, True, False, False, True],
        )
        chosen = ranked.iloc[0].copy()
        chosen["selection_rank_rule"] = (
            "seen gates; no literal hardcoding; reset usage; cross-representation agreement; neutral hash tie-break"
        )
        rows.append(chosen)
    selected = pd.DataFrame(rows).reset_index(drop=True)
    keep = KEY + ["assertion_text", "all_seen_gates_pass", "seen_gate_pass_count"] + SELECTION_FEATURES + ["selection_rank_rule"]
    return selected[keep]


def selection_digest(selected: pd.DataFrame) -> str:
    identity = selected[KEY + ["assertion_text"]].sort_values(KEY).to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def build_shadow_without_heldout(features_input: pd.DataFrame, cases_root: Path, shadow_root: Path) -> None:
    for case in sorted(features_input["case_id"].unique()):
        target = shadow_root / case
        target.mkdir(parents=True, exist_ok=True)
        for name in ("correct.v", "waveform_good.csv"):
            source = cases_root / case / name
            if source.exists():
                shutil.copy2(source, target / name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seen-only raw/temporal candidate reranker with held-out isolation audit.")
    parser.add_argument("--base-results", default=str(DEFAULT_BASE))
    parser.add_argument("--extension-results", default=str(DEFAULT_EXTENSION))
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES))
    parser.add_argument("--parent-map", default=str(DEFAULT_PARENT_MAP))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    base, extension = Path(args.base_results).resolve(), Path(args.extension_results).resolve()
    cases_root, out_dir = Path(args.cases_root).resolve(), Path(args.out_dir).resolve()
    parent_map_path = Path(args.parent_map).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    base_df = pd.read_csv(base, encoding="utf-8-sig")
    extension_df = pd.read_csv(extension, encoding="utf-8-sig")
    raw = pd.concat([base_df, extension_df], ignore_index=True)
    raw["representation"] = raw["method"].map(lambda value: "raw" if "raw" in str(value).lower() else "temporal")
    if len(raw) != 1920:
        raise RuntimeError(f"Expected 1920 source candidates, found {len(raw)}")

    feature_input = raw.drop(columns=[c for c in HELDOUT_COLUMNS if c in raw.columns])
    features = compute_selection_features(feature_input, cases_root)
    selected = select_candidates(features)
    full_digest = selection_digest(selected)

    with tempfile.TemporaryDirectory(prefix="reranker_no_heldout_") as temp:
        shadow = Path(temp)
        build_shadow_without_heldout(feature_input, cases_root, shadow)
        shadow_features = compute_selection_features(feature_input.copy(), shadow)
        shadow_selected = select_candidates(shadow_features)
        shadow_digest = selection_digest(shadow_selected)
        heldout_files = list(shadow.rglob("*holdout*")) + list(shadow.rglob("*heldout*"))
    invariant = full_digest == shadow_digest
    if not invariant or heldout_files:
        raise RuntimeError("Held-out deletion invariance audit failed")

    evaluation_cols = KEY + [c for c in HELDOUT_COLUMNS if c in raw.columns]
    evaluation = raw[evaluation_cols].copy()
    evaluation["candidate_index"] = pd.to_numeric(evaluation["candidate_index"]).astype(int)
    final = selected.merge(evaluation, on=KEY, how="left", validate="one_to_one")
    parent_records = json.loads(parent_map_path.read_text(encoding="utf-8"))
    parent_lookup = {
        str(item["case_id"]): str(item["parent_bug_id"])
        for item in parent_records
    }
    final["parent_bug_id"] = final["case_id"].map(parent_lookup)
    if final["parent_bug_id"].isna().any():
        raise RuntimeError("Missing parent_bug_id for selected cases")
    for col in ("heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous"):
        final[col] = truth(final[col])
    final["heldout_strict_success"] = (
        final["heldout_correct_pass"] & final["heldout_buggy_fail"]
        & final["heldout_antecedent_hit"] & final["heldout_non_vacuous"]
    )

    feature_path = out_dir / "selection_features_seen_only.csv"
    selected_path = out_dir / "selected_candidates_seen_only.csv"
    final_path = out_dir / "selected_candidates_final_heldout_evaluation.csv"
    summary_path = out_dir / "reranker_summary.csv"
    audit_path = out_dir / "heldout_deletion_invariance_audit.json"
    freeze_path = out_dir / "seen_only_reranker_freeze.json"
    features.drop(columns=["_canonical"]).to_csv(feature_path, index=False, encoding="utf-8-sig")
    selected.to_csv(selected_path, index=False, encoding="utf-8-sig")
    final.to_csv(final_path, index=False, encoding="utf-8-sig")
    summary = final.groupby(["model_label", "model_name"], as_index=False).agg(
        case_count=("case_id", "nunique"),
        parent_count=("parent_bug_id", "nunique"),
        selected_seen_gate_pass_count=("all_seen_gates_pass", "sum"),
        heldout_strict_success_count=("heldout_strict_success", "sum"),
        heldout_strict_success_rate=("heldout_strict_success", "mean"),
    )
    summary["k_source"] = 8
    summary["selection_uses_heldout"] = False
    summary["overlap"] = "same 120 cases across models; parent mapping not collapsed in this selection report"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    audit = {
        "schema_version": 1,
        "status": "pass",
        "audit": "selection rerun against a shadow cases root containing no held-out files",
        "heldout_files_in_shadow": 0,
        "full_selection_sha256": full_digest,
        "no_heldout_files_selection_sha256": shadow_digest,
        "selection_identical": invariant,
        "selection_feature_allowlist": SELECTION_FEATURES,
        "heldout_join_timing": "after candidate selection",
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    frozen = [base, extension, parent_map_path, feature_path, selected_path, final_path, summary_path, audit_path]
    freeze = {
        "schema_version": 1,
        "status": "frozen_seen_only_reranker",
        "source_candidate_count": len(raw),
        "selected_candidate_count": len(selected),
        "selection_feature_allowlist": SELECTION_FEATURES,
        "selection_uses_heldout": False,
        "heldout_deletion_invariance": invariant,
        "sha256": {str(path): sha(path) for path in frozen},
    }
    freeze_path.write_text(json.dumps(freeze, indent=2, ensure_ascii=False), encoding="utf-8")
    print(summary.to_string(index=False))
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    print(freeze_path)


if __name__ == "__main__":
    main()
