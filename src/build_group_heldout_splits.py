from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/formal_group_heldout_splits_v1"
OLD_MANIFEST = ROOT / "rtl_cases_real_scale120/case_manifest.json"
PARENT_MAP = ROOT / "outputs/dev_locked_score_reranker/selected_candidates.csv"
NEW_ROOTS = [ROOT / "rtl_cases_real_scale210_independent", ROOT / "rtl_cases_real_scale210_independent_next"]
SCHEMES = {
    "parent_held_out": "parent_bug_id",
    "module_held_out": "source_module",
    "bug_family_held_out": "bug_family",
    "source_project_held_out": "source_project",
}
SPLITS = ("train", "dev", "test")
TARGET = {"train": 0.60, "dev": 0.20, "test": 0.20}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_universe() -> tuple[pd.DataFrame, list[Path]]:
    old = pd.DataFrame(json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))["cases"]).rename(columns={"name": "case_id"})
    parent = pd.read_csv(PARENT_MAP, encoding="utf-8-sig")[["case_id", "parent_bug_id"]].drop_duplicates("case_id")
    old = old.merge(parent, on="case_id", how="left")
    old["dataset_root"] = "rtl_cases_real_scale120"
    old["admission_source"] = "formal scale120 universe; variants grouped by frozen parent map"
    frames = [old[["case_id", "parent_bug_id", "source_project", "source_module", "bug_family", "bug_class", "dataset_root", "admission_source"]]]
    inputs = [OLD_MANIFEST, PARENT_MAP]
    for root in NEW_ROOTS:
        manifest_path = root / "independent_new_bug_manifest.json"
        admission_path = root / "hardness_admission_report.csv"
        manifest = pd.DataFrame(json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]).rename(columns={"name": "case_id"})
        admission = pd.read_csv(admission_path, encoding="utf-8-sig")
        admitted = admission[admission.decision == "admitted"][["case_name", "parent_bug_id"]]
        frame = manifest.merge(admitted, left_on="case_id", right_on="case_name", suffixes=("", "_admission"))
        frame["parent_bug_id"] = frame.parent_bug_id_admission
        frame["dataset_root"] = root.name
        frame["admission_source"] = str(admission_path.resolve())
        frames.append(frame[["case_id", "parent_bug_id", "source_project", "source_module", "bug_family", "bug_class", "dataset_root", "admission_source"]])
        inputs.extend([manifest_path, admission_path])
    universe = pd.concat(frames, ignore_index=True)
    if universe.case_id.duplicated().any(): raise RuntimeError("Duplicate case_id in split universe")
    required = ["parent_bug_id", "source_project", "source_module", "bug_family"]
    if universe[required].isna().any().any(): raise RuntimeError("Missing grouping metadata in split universe")
    inconsistent = {c: int((universe.groupby("parent_bug_id")[c].nunique() > 1).sum()) for c in required[1:]}
    if any(inconsistent.values()): raise RuntimeError(f"Parent metadata inconsistent: {inconsistent}")
    return universe.sort_values("case_id").reset_index(drop=True), inputs


def group_assignment(universe: pd.DataFrame, column: str) -> dict[str, str]:
    sizes = universe.groupby(column).size().to_dict()
    # Stable hash breaks equal-size ties without depending on filesystem order.
    groups = sorted(sizes, key=lambda x: (-sizes[x], hashlib.sha256(f"split-v1:{column}:{x}".encode()).hexdigest()))
    if len(groups) < 3: raise RuntimeError(f"{column} has fewer than three groups")
    totals = {s: 0 for s in SPLITS}; desired = {s: TARGET[s] * len(universe) for s in SPLITS}; assignment = {}
    # Seed every split, then greedily minimize normalized fill.
    for group, split in zip(groups[:3], SPLITS): assignment[str(group)] = split; totals[split] += sizes[group]
    for group in groups[3:]:
        split = min(SPLITS, key=lambda s: (totals[s] / desired[s], totals[s], s))
        assignment[str(group)] = split; totals[split] += sizes[group]
    return assignment


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", default=str(OUT)); args = ap.parse_args()
    out = Path(args.out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    universe, inputs = load_universe(); universe_path = out / "split_universe.csv"; universe.to_csv(universe_path, index=False, encoding="utf-8-sig")
    output_paths = [universe_path]; summaries = {}
    for scheme, column in SCHEMES.items():
        assignment = group_assignment(universe, column)
        frame = universe.copy(); frame["split"] = frame[column].astype(str).map(assignment); frame["heldout_group_type"] = column; frame["heldout_group_value"] = frame[column]
        path = out / f"{scheme}.csv"; frame.to_csv(path, index=False, encoding="utf-8-sig"); output_paths.append(path)
        variants = frame.loc[frame.index.repeat(3)].copy(); variants["trace_variant"] = [x for _ in range(len(frame)) for x in ("primary", "heldout", "decoy")]
        variant_path = out / f"{scheme}_trace_variants.csv"; variants.to_csv(variant_path, index=False, encoding="utf-8-sig"); output_paths.append(variant_path)
        summaries[scheme] = {
            "group_column": column,
            "case_counts": frame.split.value_counts().reindex(SPLITS, fill_value=0).to_dict(),
            "parent_counts": frame.groupby("split").parent_bug_id.nunique().reindex(SPLITS, fill_value=0).to_dict(),
            "heldout_group_counts": frame.groupby("split")[column].nunique().reindex(SPLITS, fill_value=0).to_dict(),
            "assignment": assignment,
        }
    manifest = {
        "schema_version": 1, "status": "built_pending_leakage_audit", "seed": "sha256 split-v1",
        "case_count": len(universe), "parent_count": int(universe.parent_bug_id.nunique()),
        "project_count": int(universe.source_project.nunique()), "module_count": int(universe.source_module.nunique()), "bug_family_count": int(universe.bug_family.nunique()),
        "rejected_cases_included": False, "all_trace_variants_follow_case_split": True,
        "schemes": summaries,
        "input_sha256": {str(p.resolve()): sha(p) for p in inputs},
        "output_sha256": {str(p): sha(p) for p in output_paths},
    }
    manifest_path = out / "split_manifest.json"; manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(manifest_path)


if __name__ == "__main__": main()
