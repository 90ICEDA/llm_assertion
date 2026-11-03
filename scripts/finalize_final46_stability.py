#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "outputs/final46_stability"
OUT = REPO / "deliverables/final46_significance_stability_20260807"
CONDITIONS = {
    "baseline_s20260806_t02": (20260806, 0.2),
    "seed_s20260807_t02": (20260807, 0.2),
    "seed_s20260808_t02": (20260808, 0.2),
    "temp_s20260806_t06": (20260806, 0.6),
    "temp_s20260806_t09": (20260806, 0.9),
}
MODELS = {"GPT": "gpt-5.4", "Claude": "claude-opus-4-8", "Qwen": "qwen/qwen-2.5-72b-instruct"}
METHODS = {
    "spec_only": "spec_only", "spec_rtl_full": "full_rtl",
    "spec_rtl_signal_list": "signal_list", "spec_rtl_sliced": "rtl_slice",
    "spec_rtl_raw_trace": "raw_trace", "spec_rtl_naive_summary": "naive_summary",
    "spec_rtl_event_abstraction": "event_abstraction",
    "spec_rtl_temporal_relation_abstraction": "temporal_abstraction",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_all() -> tuple[pd.DataFrame, list[dict]]:
    frames, sources = [], []
    for condition, (seed, temperature) in CONDITIONS.items():
        for model, model_id in MODELS.items():
            for family in ("context", "trace"):
                path = ROOT / condition / model / family / "multi_model_results_raw.csv"
                if not path.is_file():
                    raise SystemExit(f"missing shard: {path}")
                frame = pd.read_csv(path, encoding="utf-8-sig")
                frame["condition"] = condition
                frame["seed"] = seed
                frame["temperature"] = temperature
                frame["model"] = model
                frame["model_id"] = model_id
                frame["method_native"] = frame["method"]
                frame["method"] = frame["method"].map(METHODS)
                frame["success"] = frame["failure_mode"].astype(str).eq("success")
                frame["candidate_index"] = pd.to_numeric(frame["candidate_index"], errors="raise").astype(int)
                frames.append(frame)
                sources.append({"condition": condition, "model": model, "family": family,
                                "rows": len(frame), "sha256": sha(path), "path": str(path.relative_to(REPO))})
    return pd.concat(frames, ignore_index=True), sources


def main() -> None:
    detail, sources = load_all()
    key = ["condition", "model", "case_id", "method", "candidate_index"]
    cell_key = ["condition", "model", "case_id", "method"]
    duplicates = int(detail.duplicated(key).sum())
    cells = detail.groupby(cell_key)["candidate_index"].agg(list)
    bad_cells = [list(idx) for idx, values in cells.items() if sorted(values) != [1, 2, 3, 4]]
    expected_rows = len(CONDITIONS) * len(MODELS) * 46 * len(METHODS) * 4
    expected_cells = len(CONDITIONS) * len(MODELS) * 46 * len(METHODS)
    model_ids_ok = all(set(detail.loc[detail.model == m, "model_name"].astype(str)) == {mid}
                       for m, mid in MODELS.items())
    complete = (len(detail) == expected_rows and len(cells) == expected_cells and duplicates == 0
                and not bad_cells and model_ids_ok and detail["method"].notna().all())
    audit = {"status": "complete" if complete else "incomplete", "analysis_unit": "parent_bug_id",
             "trace_variants_count_as_independent": False, "expected_rows": expected_rows,
             "actual_rows": len(detail), "expected_cells": expected_cells, "actual_cells": len(cells),
             "duplicate_keys": duplicates, "bad_budget_cells": len(bad_cells), "model_ids_locked": model_ids_ok,
             "sources": sources}
    OUT.mkdir(parents=True, exist_ok=True)
    if not complete:
        (OUT / "stability_incomplete.json").write_text(json.dumps({**audit, "bad_cells": bad_cells[:100]}, indent=2) + "\n")
        raise SystemExit(f"stability incomplete: {audit}")

    # Resolve parent identity from the final admitted manifest. One case maps
    # to one independent parent; trace variants never appear as rows here.
    manifest = json.loads((REPO / "deliverables/final_dataset_acceptance_20260804/final_manifest.json").read_text())
    parents = {x["name"]: x["parent_bug_id"] for x in manifest["cases"]}
    detail["parent_bug_id"] = detail["case_id"].map(parents)
    if detail["parent_bug_id"].isna().any() or detail["parent_bug_id"].nunique() != 46:
        raise SystemExit("parent mapping failed")

    rows = []
    for k in range(1, 5):
        use = detail.loc[detail.candidate_index <= k]
        for keys, group in use.groupby(["condition", "seed", "temperature", "model", "model_id", "method"], sort=True):
            condition, seed, temperature, model, model_id, method = keys
            parent = group.groupby("parent_bug_id")["success"].any()
            axis = "baseline" if condition.startswith("baseline_") else "seed" if condition.startswith("seed_") else "temperature"
            rows.append({"ablation_axis": axis, "condition": condition, "seed": seed,
                         "temperature": temperature, "k": k, "model": model, "model_id": model_id,
                         "method": method, "n_parent_bugs": parent.size,
                         "candidate_count": len(group), "candidate_success_count": int(group.success.sum()),
                         "candidate_success_rate": float(group.success.mean()),
                         "parent_any_of_k_success_count": int(parent.sum()),
                         "parent_any_of_k_success_rate": float(parent.mean()),
                         "trace_variants_count_as_independent": False})
    ablation = pd.DataFrame(rows).sort_values(["ablation_axis", "model", "method", "condition", "k"])
    ablation.to_csv(OUT / "seed_temperature_k_ablation.csv", index=False, encoding="utf-8-sig")

    # Stability ranges at the preregistered k=4.  Seed comparisons hold t=.2;
    # temperature comparisons hold seed=20260806.
    stable_rows = []
    k4 = ablation.loc[ablation.k == 4]
    for axis, subset in (("seed", k4.loc[k4.temperature == 0.2]),
                         ("temperature", k4.loc[k4.seed == 20260806])):
        for (model, method), group in subset.groupby(["model", "method"], sort=True):
            values = group.parent_any_of_k_success_rate
            stable_rows.append({"ablation_axis": axis, "model": model, "method": method,
                                "condition_count": len(group), "n_parent_bugs_per_condition": 46,
                                "mean_parent_any_of_4_rate": float(values.mean()),
                                "std_parent_any_of_4_rate": float(values.std(ddof=1)),
                                "min_parent_any_of_4_rate": float(values.min()),
                                "max_parent_any_of_4_rate": float(values.max()),
                                "range_parent_any_of_4_rate": float(values.max() - values.min())})
    pd.DataFrame(stable_rows).to_csv(OUT / "seed_temperature_stability_summary.csv", index=False, encoding="utf-8-sig")

    audit.update({"status": "complete", "ablation_rows": len(ablation),
                  "stability_summary_rows": len(stable_rows), "parent_count": 46})
    (OUT / "stability_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    files = [p for p in OUT.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt"]
    (OUT / "SHA256SUMS.txt").write_text("\n".join(f"{sha(p)}  {p.name}" for p in sorted(files)) + "\n")
    print(json.dumps({k: audit[k] for k in ("status", "expected_rows", "actual_rows", "expected_cells",
                                             "actual_cells", "duplicate_keys", "bad_budget_cells",
                                             "ablation_rows", "stability_summary_rows")}, indent=2))


if __name__ == "__main__":
    main()
