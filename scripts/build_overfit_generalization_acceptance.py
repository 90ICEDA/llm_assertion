from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables/overfit_challenge_generalization_20260810"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_json = json.loads((ROOT / "rtl_cases_overfit_bait20/overfit20_manifest.json").read_text(encoding="utf-8"))
    manifest = pd.json_normalize(manifest_json["cases"])
    manifest["heldout_source_cases"] = manifest["heldout_source_cases"].map(lambda x: " | ".join(x))
    manifest["heldout_bait_values"] = manifest["heldout_bait_values"].map(lambda x: " | ".join(map(str, x)))
    manifest["challenge_axis"] = "value_renaming"
    manifest["evidence_status"] = "executed"
    manifest.to_csv(OUT / "overfit_challenge_manifest.csv", index=False, encoding="utf-8-sig")

    results = pd.read_csv(ROOT / "outputs/overfit_bait20_evaluation/multi_heldout_candidate_results.csv", encoding="utf-8-sig")
    meta = manifest[["case_id", "parent_bug_id", "bait_kind", "bait_signal", "challenge_axis"]]
    results = results.merge(meta, on="case_id", how="left")
    results.to_csv(OUT / "overfit_challenge_results.csv", index=False, encoding="utf-8-sig")
    stats = results.groupby(["bait_kind", "challenge_axis"], as_index=False).agg(
        candidate_count=("case_id", "size"), case_count=("case_id", "nunique"), parent_count=("parent_bug_id", "nunique"),
        primary_success=("primary_success", "sum"), generalized_all_3=("all_three_heldouts_generalize", "sum"),
        behavioral_overfit=("behavioral_overfit", "sum"), regex_hardcoding=("regex_literal_hardcoding_auxiliary", "sum"),
    )
    stats.to_csv(OUT / "overfit_type_statistics.csv", index=False, encoding="utf-8-sig")

    hard = pd.read_csv(ROOT / "outputs/preference_pairs_v1/generalization_hard_pairs.csv", encoding="utf-8-sig")
    hard.to_csv(OUT / "hard_preference_pairs.csv", index=False, encoding="utf-8-sig")
    with (OUT / "hard_preference_pairs.jsonl").open("w", encoding="utf-8") as h:
        for row in hard.to_dict(orient="records"):
            h.write(json.dumps(row, ensure_ascii=False) + "\n")
    dist = hard.groupby(["chosen_model", "rejected_model", "chosen_representation", "rejected_representation"], dropna=False).size().reset_index(name="pair_count")
    dist.to_csv(OUT / "hard_pair_distribution.csv", index=False, encoding="utf-8-sig")

    split_root = ROOT / "outputs/formal_group_heldout_splits_v1"
    scheme_files = {"parent": "parent_held_out.csv", "module": "module_held_out.csv", "family": "bug_family_held_out.csv", "project": "source_project_held_out.csv"}
    split_frames = []
    for scheme, filename in scheme_files.items():
        f = pd.read_csv(split_root / filename, encoding="utf-8-sig")
        f.insert(0, "scheme", scheme)
        split_frames.append(f)
    splits = pd.concat(split_frames, ignore_index=True)
    splits.to_csv(OUT / "split_manifest.csv", index=False, encoding="utf-8-sig")
    shutil.copy2(split_root / "leakage_audit.json", OUT / "automatic_leakage_audit.json")

    coverage = pd.DataFrame([
        ["fixed count value", False, "missing", "no executed challenge row"],
        ["address", True, "executed", "legal fixed address; 3 held-outs/case"],
        ["state encoding", True, "executed", "legal fixed onehot/state value; 3 held-outs/case"],
        ["request pattern", False, "missing", "no executed challenge row"],
        ["FIFO depth", False, "missing", "no executed challenge row"],
        ["lane index", False, "missing", "no executed challenge row"],
        ["value renaming", True, "executed", "four distinct legal values: primary + 3 held-outs"],
        ["width scaling", False, "missing", "no width-scaled RTL/testbench evidence"],
        ["parameter scaling", False, "missing", "no parameter-scaled RTL/testbench evidence"],
    ], columns=["requirement", "complete", "status", "evidence"])
    coverage.to_csv(OUT / "acceptance_coverage_and_gaps.csv", index=False, encoding="utf-8-sig")

    audit = json.loads((OUT / "automatic_leakage_audit.json").read_text(encoding="utf-8"))
    summary = {
        "status": "partial_not_accepted",
        "challenge_cases": int(manifest.case_id.nunique()), "challenge_parents": int(manifest.parent_bug_id.nunique()),
        "minimum_heldouts": int(manifest.heldout_count.min()), "candidate_results": len(results),
        "behavioral_overfit": int(results.behavioral_overfit.astype(bool).sum()),
        "hard_pairs": len(hard), "hard_pair_cases": int(hard.case_id.nunique()), "hard_pair_parents": int(hard.parent_bug_id.nunique()),
        "split_rows": len(splits), "split_leakage_all_pass": bool(audit["all_pass"]),
        "completed_requirements": coverage.loc[coverage.complete, "requirement"].tolist(),
        "missing_requirements": coverage.loc[~coverage.complete, "requirement"].tolist(),
    }
    (OUT / "acceptance_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    sources = [ROOT / "rtl_cases_overfit_bait20/overfit20_manifest.json", ROOT / "outputs/overfit_bait20_evaluation/multi_heldout_candidate_results.csv", ROOT / "outputs/preference_pairs_v1/generalization_hard_pairs.csv", split_root / "split_manifest.json", split_root / "leakage_audit.json"]
    freeze = {"source_sha256": {str(p): sha(p) for p in sources}, "output_sha256": {p.name: sha(p) for p in OUT.iterdir() if p.is_file()}}
    (OUT / "artifact_hashes.json").write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    report = f"""# 过拟合挑战集与泛化数据验收\n\n结论：**未完美完成，当前为部分验收**。已有 20 个 challenge case、每个 3 条 held-out；但只覆盖地址/状态值与 value renaming，缺少 fixed count、request pattern、FIFO depth、lane index、width scaling、parameter scaling 的真实执行证据。\n\n- 候选结果：{len(results)} 条；行为过拟合 {summary['behavioral_overfit']} 条。\n- hard preference pairs：{len(hard)} 对，覆盖 {summary['hard_pair_cases']} cases / {summary['hard_pair_parents']} parents；契约为 visible 两者均成功、held-out 恰好一成一败。\n- split：parent/module/family/project 四套，自动泄漏审计 all_pass={audit['all_pass']}。\n- 因缺项存在，本报告不把挑战集标记为验收通过。\n"""
    (OUT / "README.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
