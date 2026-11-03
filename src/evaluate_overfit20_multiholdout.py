from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from run_multi_model_small_eval import literal_hardcoding_flag
from run_trace_abstraction_prototype import run_case_eval


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "rtl_cases_overfit_bait20"
DEFAULT_OUT = ROOT / "outputs/overfit_bait20_evaluation"


def allowed_signals(case_dir: Path) -> list[str]:
    with (case_dir / "waveform_good.csv").open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    return [x.split("[", 1)[0].strip() for x in header if x.strip() != "time_ps"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, help="CSV columns: model,case_id,candidate_index,assertion_text")
    ap.add_argument("--cases-root", default=str(DEFAULT_CASES)); ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    cases_root, out_dir = Path(args.cases_root).resolve(), Path(args.out_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = Path(args.candidates).resolve(); candidates = pd.read_csv(candidates_path, encoding="utf-8-sig")
    required = {"model", "case_id", "candidate_index", "assertion_text"}
    if not required.issubset(candidates.columns): raise RuntimeError(f"Missing columns: {sorted(required-set(candidates.columns))}")
    rows = []
    for item in candidates.itertuples(index=False):
        case_dir = cases_root / item.case_id
        variant_results = []
        for heldout_index in range(0, 4):
            with tempfile.TemporaryDirectory(prefix="overfit20_eval_") as tmp:
                shadow = Path(tmp) / item.case_id; shutil.copytree(case_dir, shadow)
                if heldout_index:
                    shutil.copy2(case_dir / f"tb_holdout_{heldout_index}.v", shadow / "tb_holdout.v")
                else:
                    shutil.copy2(case_dir / "tb.v", shadow / "tb_holdout.v")
                result = run_case_eval(case_id=item.case_id, assertion_text=item.assertion_text, signal_names=allowed_signals(case_dir), use_property=False, runtime_dir=out_dir / "runtime" / str(item.model) / item.case_id / f"candidate_{item.candidate_index}" / f"variant_{heldout_index}", cases_root=shadow.parent)
            variant_results.append(result)
        primary = variant_results[0]
        heldouts = variant_results[1:]
        behavioral_generalization = all(r["heldout_correct_pass"] and r["heldout_buggy_fail"] and r["heldout_antecedent_hit"] and r["heldout_non_vacuous"] for r in heldouts)
        rows.append({
            "model": item.model, "case_id": item.case_id, "candidate_index": item.candidate_index,
            "assertion_text": item.assertion_text, "regex_literal_hardcoding_auxiliary": literal_hardcoding_flag(item.assertion_text),
            "primary_success": primary["correct_pass"] and primary["buggy_fail"] and primary["antecedent_hit"] and primary["non_vacuous"],
            **{f"heldout_{i}_success": r["heldout_correct_pass"] and r["heldout_buggy_fail"] and r["heldout_antecedent_hit"] and r["heldout_non_vacuous"] for i, r in enumerate(heldouts, 1)},
            "all_three_heldouts_generalize": behavioral_generalization,
            "behavioral_overfit": bool(primary["correct_pass"] and primary["buggy_fail"] and not behavioral_generalization),
        })
    result_path = out_dir / "multi_heldout_candidate_results.csv"; pd.DataFrame(rows).to_csv(result_path, index=False, encoding="utf-8-sig")
    summary = pd.DataFrame(rows).groupby("model", as_index=False).agg(candidate_count=("case_id", "size"), primary_success_count=("primary_success", "sum"), all_three_heldouts_generalize_count=("all_three_heldouts_generalize", "sum"), behavioral_overfit_count=("behavioral_overfit", "sum"), regex_hardcoding_count=("regex_literal_hardcoding_auxiliary", "sum"))
    summary_path = out_dir / "multi_heldout_summary.csv"; summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    freeze_path = out_dir / "overfit20_evaluation_freeze.json"; freeze_path.write_text(json.dumps({"status":"frozen","generalization_definition":"actual procedural evaluation passes correct and detects buggy behavior on all 3 held-outs","regex_is_decisive":False,"sha256":{str(p):sha(p) for p in [candidates_path,result_path,summary_path,cases_root/'overfit20_manifest.json']}},indent=2),encoding="utf-8")
    print(summary.to_string(index=False)); print(freeze_path)


if __name__ == "__main__": main()
