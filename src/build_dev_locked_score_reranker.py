from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import pandas as pd

from build_seen_only_candidate_reranker import (
    DEFAULT_BASE, DEFAULT_CASES, DEFAULT_EXTENSION, DEFAULT_PARENT_MAP,
    KEY, canonical_assertion, compute_selection_features, truth,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPLIT = ROOT / "outputs/formal_trace_router/locked_policy.json"
DEFAULT_OUT = ROOT / "outputs/dev_locked_score_reranker"
WEIGHT_NAMES = [
    "compile", "seen_correct", "seen_buggy_fail", "antecedent_hit", "non_vacuous",
    "signal_exists", "reset_ok", "cross_representation_agreement",
    "hardcoding", "unsupported",
]


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def candidate_table(base: Path, extension: Path, cases_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.concat([pd.read_csv(base, encoding="utf-8-sig"), pd.read_csv(extension, encoding="utf-8-sig")], ignore_index=True)
    raw["representation"] = raw["method"].map(lambda x: "raw" if "raw" in str(x).lower() else "temporal")
    feature_input = raw.drop(columns=[c for c in raw if "heldout" in c or c == "trace_overfit"])
    features = compute_selection_features(feature_input, cases_root)
    features["hardcoding"] = features["literal_hardcoding"]
    features["unsupported"] = ~features["parser_support"]
    evaluation = raw[KEY + ["heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous", "trace_overfit"]].copy()
    evaluation["candidate_index"] = pd.to_numeric(evaluation["candidate_index"]).astype(int)
    for col in ["heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous", "trace_overfit"]:
        evaluation[col] = truth(evaluation[col])
    return features, evaluation


def score(df: pd.DataFrame, w: dict[str, int]) -> pd.Series:
    return (
        w["compile"] * df["compile_ok"].astype(int)
        + w["seen_correct"] * df["seen_good_pass"].astype(int)
        + w["seen_buggy_fail"] * df["seen_bad_fail"].astype(int)
        + w["antecedent_hit"] * df["seen_antecedent_hit"].astype(int)
        + w["non_vacuous"] * df["non_vacuous"].astype(int)
        + w["signal_exists"] * df["signal_exists"].astype(int)
        + w["reset_ok"] * df["reset_usage"].astype(int)
        + w["cross_representation_agreement"] * df["cross_representation_agreement"].astype(int)
        + w["hardcoding"] * df["hardcoding"].astype(int)
        + w["unsupported"] * df["unsupported"].astype(int)
    )


def select(features: pd.DataFrame, weights: dict[str, int], case_ids: set[str]) -> pd.DataFrame:
    data = features.loc[features["case_id"].isin(case_ids)].copy()
    data["score"] = score(data, weights)
    data["_tie"] = data.apply(lambda r: sha_bytes(f"score-reranker-v1|{r['representation']}|{r['candidate_index']}|{canonical_assertion(r['assertion_text'])}".encode()), axis=1)
    group = ["model_label", "provider", "model_name", "case_id"]
    selected = data.sort_values(group + ["score", "_tie"], ascending=[True, True, True, True, False, True]).groupby(group, as_index=False, sort=False).head(1)
    return selected


def join_eval(selected: pd.DataFrame, evaluation: pd.DataFrame) -> pd.DataFrame:
    out = selected.merge(evaluation, on=KEY, how="left", validate="one_to_one")
    out["heldout_detect"] = out["heldout_buggy_fail"] & out["heldout_antecedent_hit"] & out["heldout_non_vacuous"]
    out["heldout_success"] = out["heldout_correct_pass"] & out["heldout_buggy_fail"]
    out["strict_success"] = out["heldout_correct_pass"] & out["heldout_detect"]
    return out


def objective(selected_eval: pd.DataFrame) -> tuple:
    return (
        int(selected_eval["strict_success"].sum()),
        -int((~selected_eval["heldout_correct_pass"]).sum()),
        -int((~selected_eval["heldout_detect"]).sum()),
        -int(selected_eval["hardcoding"].sum()),
    )


def weight_grid():
    for values in itertools.product(
        [1, 2], [2, 3], [2, 3], [1, 2], [1, 2], [1], [0, 1], [0, 1], [-2, -1], [-4, -2]
    ):
        yield dict(zip(WEIGHT_NAMES, values))


def fit_dev(features: pd.DataFrame, evaluation: pd.DataFrame, dev_parent_ids: list[str]) -> tuple[dict[str, int], pd.DataFrame]:
    dev_ids = set(dev_parent_ids)  # primary parent cases: one independent row per bug
    trials = []
    best_weights = None; best_obj = None
    for index, weights in enumerate(weight_grid(), start=1):
        result = join_eval(select(features, weights, dev_ids), evaluation)
        obj = objective(result)
        trials.append({"trial": index, **weights, "strict_success_count": obj[0], "FPR_count": -obj[1], "MDR_count": -obj[2], "hardcoding_selected_count": -obj[3]})
        key = (obj, tuple(-weights[name] for name in WEIGHT_NAMES))
        if best_obj is None or key > best_obj:
            best_obj, best_weights = key, weights
    assert best_weights is not None
    return best_weights, pd.DataFrame(trials)


def metrics(data: pd.DataFrame, scope: str, split: str, policy_sha: str) -> pd.DataFrame:
    rows = []
    for (model, model_name), sub in data.groupby(["model_label", "model_name"]):
        n = len(sub)
        rows.append({
            "split": split, "scope": scope, "model": model, "model_name": model_name,
            "k": 8, "sample_count": n, "parent_count": int(sub["parent_bug_id"].nunique()),
            "deduplicated": scope == "parent_primary", "overlap": "parent-disjoint dev/test; same parents across models",
            "coverage": 1.0, "abstain_rate": 0.0,
            "overall_success": float(sub["strict_success"].mean()), "conditional_success": float(sub["strict_success"].mean()),
            "FPR": float((~sub["heldout_correct_pass"]).mean()), "MDR": float((~sub["heldout_detect"]).mean()),
            "heldout_success": float(sub["heldout_success"].mean()), "overfit": float(sub["trace_overfit"].mean()),
            "policy_sha256": policy_sha,
        })
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--base-results", default=str(DEFAULT_BASE)); ap.add_argument("--extension-results", default=str(DEFAULT_EXTENSION)); ap.add_argument("--cases-root", default=str(DEFAULT_CASES)); ap.add_argument("--parent-map", default=str(DEFAULT_PARENT_MAP)); ap.add_argument("--split-policy", default=str(DEFAULT_SPLIT)); ap.add_argument("--out-dir", default=str(DEFAULT_OUT)); args = ap.parse_args()
    base, extension, cases_root = Path(args.base_results).resolve(), Path(args.extension_results).resolve(), Path(args.cases_root).resolve()
    parent_path, split_path, out_dir = Path(args.parent_map).resolve(), Path(args.split_policy).resolve(), Path(args.out_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = out_dir / "score_policy_lock.json"; trials_path = out_dir / "dev_weight_search.csv"
    features, evaluation = candidate_table(base, extension, cases_root)
    split = json.loads(split_path.read_text(encoding="utf-8")); dev_parents, test_parents = split["dev_parent_ids"], split["test_parent_ids"]
    if set(dev_parents) & set(test_parents): raise RuntimeError("Dev/test parent overlap")
    if lock_path.exists():
        lock = json.loads(lock_path.read_text(encoding="utf-8")); weights = lock["weights"]
        if lock["dev_parent_ids"] != dev_parents or lock["test_parent_ids"] != test_parents: raise RuntimeError("Locked split mismatch")
    else:
        weights, trials = fit_dev(features, evaluation, dev_parents); trials.to_csv(trials_path, index=False, encoding="utf-8-sig")
        lock = {"schema_version":1, "locked":True, "fit_scope":"dev_parent_primary_only", "objective":"maximize dev heldout strict success; tie-break lower FPR, lower MDR, fewer hardcoded selections", "weights":weights, "feature_signs":{"positive":[k for k,v in weights.items() if v>0],"negative":[k for k,v in weights.items() if v<0]}, "dev_parent_ids":dev_parents, "test_parent_ids":test_parents, "dev_parent_count":len(dev_parents), "test_parent_count":len(test_parents), "source_hashes":{"base":sha(base),"extension":sha(extension),"split":sha(split_path),"parent_map":sha(parent_path)}}
        lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    policy_sha = sha(lock_path)
    parent_records=json.loads(parent_path.read_text(encoding="utf-8")); parent_lookup={x["case_id"]:x["parent_bug_id"] for x in parent_records}
    outputs=[]; selected_outputs=[]
    for split_name, parents in [("dev",dev_parents),("test",test_parents)]:
        all_case_ids={case for case,parent in parent_lookup.items() if parent in set(parents)}
        selected=join_eval(select(features,weights,all_case_ids),evaluation); selected["parent_bug_id"]=selected["case_id"].map(parent_lookup); selected["split"]=split_name; selected["policy_sha256"]=policy_sha; selected_outputs.append(selected)
        outputs.append(metrics(selected,"case",split_name,policy_sha)); outputs.append(metrics(selected.loc[selected["case_id"]==selected["parent_bug_id"]],"parent_primary",split_name,policy_sha))
    selected_all=pd.concat(selected_outputs,ignore_index=True); report=pd.concat(outputs,ignore_index=True)
    selected_path=out_dir/"selected_candidates.csv"; report_path=out_dir/"dev_test_metrics.csv"; selected_all.to_csv(selected_path,index=False,encoding="utf-8-sig"); report.to_csv(report_path,index=False,encoding="utf-8-sig")
    sensitivity=[]
    locked_test=selected_all.loc[selected_all["split"]=="test"]; locked_ids={(r.model_label,r.case_id):(r.representation,int(r.candidate_index),r.assertion_text) for r in locked_test.itertuples()}
    for name in WEIGHT_NAMES:
        for delta in (-1,1):
            varied=dict(weights); varied[name]+=delta
            all_test_ids={case for case,parent in parent_lookup.items() if parent in set(test_parents)}
            result=join_eval(select(features,varied,all_test_ids),evaluation); result["parent_bug_id"]=result["case_id"].map(parent_lookup)
            current={(r.model_label,r.case_id):(r.representation,int(r.candidate_index),r.assertion_text) for r in result.itertuples()}
            for scope, sub in [("case",result),("parent_primary",result.loc[result["case_id"]==result["parent_bug_id"]])]:
                for model, model_sub in sub.groupby("model_label"):
                    keys=[k for k in current if k[0]==model and (scope=="case" or k[1] in set(test_parents))]
                    sensitivity.append({"weight":name,"delta":delta,"varied_weight":varied[name],"scope":scope,"model":model,"sample_count":len(model_sub),"selection_churn_count":sum(current[k]!=locked_ids[k] for k in keys),"selection_churn_rate":sum(current[k]!=locked_ids[k] for k in keys)/len(keys),"overall_success":float(model_sub["strict_success"].mean()),"FPR":float((~model_sub["heldout_correct_pass"]).mean()),"MDR":float((~model_sub["heldout_detect"]).mean()),"heldout_success":float(model_sub["heldout_success"].mean()),"overfit":float(model_sub["trace_overfit"].mean()),"policy_remains_locked":True})
    sensitivity_path=out_dir/"test_weight_sensitivity.csv"; pd.DataFrame(sensitivity).to_csv(sensitivity_path,index=False,encoding="utf-8-sig")
    freeze_path=out_dir/"score_reranker_freeze.json"; frozen=[base,extension,parent_path,split_path,lock_path,trials_path,selected_path,report_path,sensitivity_path]; freeze_path.write_text(json.dumps({"status":"frozen_dev_locked_score_reranker","policy_sha256":policy_sha,"test_did_not_refit":True,"sensitivity_did_not_modify_policy":True,"sha256":{str(p):sha(p) for p in frozen}},indent=2),encoding="utf-8")
    print(json.dumps(lock,indent=2)); print(report.to_string(index=False)); print(freeze_path)


if __name__ == "__main__": main()
