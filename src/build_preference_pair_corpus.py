from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/preference_pairs_v1"
PARENT_MAP = ROOT / "outputs/dev_locked_score_reranker/selected_candidates.csv"
SOURCES = [
    ROOT / "outputs/formal_compliant_four_trace_dual/multi_model_results_raw.csv",
    ROOT / "outputs/formal_compliant_raw_temporal_dual/multi_model_results_raw.csv",
    ROOT / "outputs/candidate_portfolio_k4_extension/multi_model_results_raw.csv",
    ROOT / "outputs/candidate_portfolio_formal/portfolio_strategy_candidates.csv",
    ROOT / "outputs/scale120_rtl_context_six_method_formal/multi_model_results_raw.csv",
]
ORDINARY_QUOTAS = {
    "vacuous": 167,
    "false_positive": 167,
    "missed_detection": 167,
    "compile_fail": 166,
    "too_strong": 167,
    "too_weak": 166,
}


def truth(frame: pd.DataFrame, name: str, default: bool = False) -> pd.Series:
    if name not in frame.columns:
        return pd.Series(default, index=frame.index)
    return frame[name].astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def stable_key(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(map(str, parts)).encode()).hexdigest()


def load_pool() -> pd.DataFrame:
    frames = []
    for source in SOURCES:
        if not source.exists():
            raise FileNotFoundError(source)
        frame = pd.read_csv(source, encoding="utf-8-sig")
        frame["source_file"] = str(source.resolve())
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True, sort=False)
    parent = pd.read_csv(PARENT_MAP, encoding="utf-8-sig")[["case_id", "parent_bug_id"]].drop_duplicates("case_id")
    data = data.drop(columns=["parent_bug_id"], errors="ignore").merge(parent, on="case_id", how="left")
    if data.parent_bug_id.isna().any():
        missing = sorted(data.loc[data.parent_bug_id.isna(), "case_id"].unique())
        raise RuntimeError(f"Missing parent_bug_id for: {missing[:10]}")
    data["assertion_text"] = data.assertion_text.fillna("").astype(str)
    for name in ("method", "representation"):
        if name not in data.columns: data[name] = ""
    data["canonical_assertion"] = data.assertion_text.map(canon)
    data = data[data.canonical_assertion.str.len() > 0].copy()
    data["model"] = data.get("model_label", data.get("model", "unknown")).fillna("unknown")
    data["compile"] = truth(data, "compile_ok")
    data["seen_correct"] = truth(data, "correct_pass")
    data["seen_bug_detect"] = truth(data, "buggy_fail")
    data["seen_ant"] = truth(data, "antecedent_hit_buggy", True)
    data["seen_nonvac"] = truth(data, "non_vacuous_buggy", True)
    data["held_correct"] = truth(data, "heldout_correct_pass")
    data["held_bug_detect"] = truth(data, "heldout_buggy_fail")
    data["held_ant"] = truth(data, "heldout_antecedent_hit", True)
    data["held_nonvac"] = truth(data, "heldout_non_vacuous", True)
    data["seen_success"] = data.compile & data.seen_correct & data.seen_bug_detect & data.seen_ant & data.seen_nonvac
    data["heldout_success"] = data.held_correct & data.held_bug_detect & data.held_ant & data.held_nonvac
    # Prefer the record with the most complete provenance for duplicate assertions.
    data["provenance_score"] = data[["method", "representation", "model"]].notna().sum(axis=1)
    data = data.sort_values(["case_id", "canonical_assertion", "provenance_score", "source_file"], ascending=[True, True, False, True])
    return data.drop_duplicates(["case_id", "canonical_assertion"], keep="first").reset_index(drop=True)


def row_value(row: pd.Series, name: str) -> object:
    value = row.get(name, "")
    return "" if pd.isna(value) else value


def pair_record(kind: str, category: str, chosen: pd.Series, rejected: pd.Series) -> dict:
    pair_id = stable_key(kind, category, chosen.case_id, chosen.canonical_assertion, rejected.canonical_assertion)[:24]
    result = {
        "pair_id": pair_id,
        "pair_kind": kind,
        "error_category": category,
        "case_id": chosen.case_id,
        "parent_bug_id": chosen.parent_bug_id,
        "chosen_assertion": chosen.assertion_text,
        "rejected_assertion": rejected.assertion_text,
        "chosen_model": chosen.model,
        "rejected_model": rejected.model,
        "chosen_method": row_value(chosen, "method"),
        "rejected_method": row_value(rejected, "method"),
        "chosen_representation": row_value(chosen, "representation"),
        "rejected_representation": row_value(rejected, "representation"),
        "chosen_source": chosen.source_file,
        "rejected_source": rejected.source_file,
    }
    for prefix, row in (("chosen", chosen), ("rejected", rejected)):
        for field in ("compile", "seen_correct", "seen_bug_detect", "seen_ant", "seen_nonvac", "seen_success", "held_correct", "held_bug_detect", "held_ant", "held_nonvac", "heldout_success"):
            result[f"{prefix}_{field}"] = bool(row[field])
    return result


def hard_pairs(pool: pd.DataFrame, count: int) -> pd.DataFrame:
    candidates = []
    seen = pool[pool.seen_success]
    for case_id, group in seen.groupby("case_id"):
        good, bad = group[group.heldout_success], group[~group.heldout_success]
        for _, chosen in good.iterrows():
            for _, rejected in bad.iterrows():
                candidates.append(pair_record("generalization_hard", "heldout_generalization", chosen, rejected))
    frame = pd.DataFrame(candidates)
    if len(frame) < count:
        raise RuntimeError(f"Only {len(frame)} generalization hard pairs are available; need {count}")
    # Round-robin by case prevents one large case from dominating the corpus.
    frame["sample_key"] = frame.pair_id.map(lambda x: stable_key("hard-v1", x))
    frame = frame.sort_values(["case_id", "sample_key"])
    groups = {k: list(v.index) for k, v in frame.groupby("case_id")}
    selected = []
    while len(selected) < count:
        progressed = False
        for case_id in sorted(groups):
            if groups[case_id] and len(selected) < count:
                selected.append(groups[case_id].pop(0)); progressed = True
        if not progressed: break
    return frame.loc[selected].drop(columns="sample_key").reset_index(drop=True)


def loser_category(row: pd.Series) -> str | None:
    if not row.compile: return "compile_fail"
    if not row.seen_nonvac or not row.seen_ant: return "vacuous"
    if not row.seen_correct: return "too_strong"
    if row.seen_correct and not row.seen_bug_detect: return "too_weak"
    if not row.held_correct: return "false_positive"
    if not row.held_bug_detect: return "missed_detection"
    return None


def ordinary_pairs(pool: pd.DataFrame, excluded_pairs: set[tuple[str, str, str]]) -> pd.DataFrame:
    records = []
    used_pairs: set[tuple[str, str, str]] = set(excluded_pairs)
    winners = pool[pool.heldout_success & pool.seen_success]
    for category, quota in ORDINARY_QUOTAS.items():
        possible = []
        for case_id, losers in pool.groupby("case_id"):
            good = winners[winners.case_id == case_id]
            if good.empty: continue
            losers = losers[losers.apply(loser_category, axis=1) == category]
            for _, chosen in good.iterrows():
                for _, rejected in losers.iterrows():
                    key = (case_id, chosen.canonical_assertion, rejected.canonical_assertion)
                    if chosen.canonical_assertion != rejected.canonical_assertion and key not in used_pairs:
                        possible.append((stable_key("ordinary-v1", category, *key), key, pair_record("ordinary", category, chosen, rejected)))
        possible.sort(key=lambda x: x[0])
        if len(possible) < quota:
            raise RuntimeError(f"Only {len(possible)} ordinary {category} pairs are available; need {quota}")
        # Prefer case diversity first, then fill deterministically.
        by_case: dict[str, list] = {}
        for item in possible: by_case.setdefault(item[1][0], []).append(item)
        chosen_items = []
        while len(chosen_items) < quota:
            progressed = False
            for case_id in sorted(by_case):
                if by_case[case_id] and len(chosen_items) < quota:
                    chosen_items.append(by_case[case_id].pop(0)); progressed = True
            if not progressed: break
        for _, key, record in chosen_items:
            used_pairs.add(key); records.append(record)
    return pd.DataFrame(records)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT))
    ap.add_argument("--hard-count", type=int, default=300)
    args = ap.parse_args()
    out = Path(args.out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    pool = load_pool()
    hard = hard_pairs(pool, args.hard_count)
    excluded = set(zip(hard.case_id, hard.chosen_assertion.map(canon), hard.rejected_assertion.map(canon)))
    ordinary = ordinary_pairs(pool, excluded)
    combined = pd.concat([hard, ordinary], ignore_index=True)
    if combined.pair_id.duplicated().any(): raise RuntimeError("Duplicate pair_id detected")
    semantic_keys = list(zip(combined.case_id, combined.chosen_assertion.map(canon), combined.rejected_assertion.map(canon)))
    if len(semantic_keys) != len(set(semantic_keys)): raise RuntimeError("Duplicate semantic preference pair detected")
    if (hard.chosen_seen_success.ne(True) | hard.rejected_seen_success.ne(True) | hard.chosen_heldout_success.ne(True) | hard.rejected_heldout_success.ne(False)).any():
        raise RuntimeError("Generalization-hard contract violation")
    paths = {
        "hard": out / "generalization_hard_pairs.csv",
        "ordinary": out / "ordinary_error_pairs.csv",
        "all": out / "preference_pairs.csv",
    }
    hard.to_csv(paths["hard"], index=False, encoding="utf-8-sig")
    ordinary.to_csv(paths["ordinary"], index=False, encoding="utf-8-sig")
    combined.to_csv(paths["all"], index=False, encoding="utf-8-sig")
    summary = {
        "schema_version": 1,
        "status": "frozen",
        "selection_seed": "sha256 deterministic preference-pairs-v1",
        "same_case_pairs": True,
        "duplicate_pair_count": int(combined.pair_id.duplicated().sum()),
        "duplicate_semantic_pair_count": len(semantic_keys) - len(set(semantic_keys)),
        "candidate_pool_unique_case_assertion_count": len(pool),
        "generalization_hard": {
            "pair_count": len(hard), "case_count": int(hard.case_id.nunique()), "parent_count": int(hard.parent_bug_id.nunique()),
            "definition": "both assertions pass seen; chosen passes held-out and rejected fails held-out",
        },
        "ordinary": {
            "pair_count": len(ordinary), "case_count": int(ordinary.case_id.nunique()), "parent_count": int(ordinary.parent_bug_id.nunique()),
            "category_counts": ordinary.error_category.value_counts().sort_index().to_dict(),
            "definition": "same-case held-out+seen successful chosen assertion versus a rejected assertion assigned one primary error category",
        },
        "source_sha256": {str(p.resolve()): sha(p) for p in [*SOURCES, PARENT_MAP]},
        "output_sha256": {str(p): sha(p) for p in paths.values()},
    }
    summary_path = out / "preference_pair_freeze.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(summary_path)


if __name__ == "__main__":
    main()
