from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


KEY = ["model_label", "provider", "model_name", "case_id", "method", "candidate_index"]
PROMPT_KEY = ["model_label", "provider", "model_name", "case_id", "method"]
REUSE = {
    "spec_rtl_raw_trace": ("spec_rtl_raw_trace", "raw_trace", Path("outputs/formal_compliant_raw_temporal_dual")),
    "spec_rtl_temporal_relation_abstraction": ("spec_rtl_temporal_relation_abstraction", "temporal_relation_abstraction", Path("outputs/formal_compliant_raw_temporal_dual")),
    "spec_rtl_naive_summary": ("spec_rtl_naive_summary", "naive_summary", Path("outputs/scale120_trace_representation_ablation_data")),
    "spec_rtl_event_abstraction": ("spec_rtl_event_level_abstraction", "event_abstraction", Path("outputs/scale120_trace_representation_ablation_data")),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upsert(current: pd.DataFrame, additions: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    combined = pd.concat([current, additions], ignore_index=True, sort=False)
    return combined.drop_duplicates(key, keep="first").sort_values(key).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reuse only representation-identical formal arms; never reuse event abstraction.")
    parser.add_argument("--output-dir", default="outputs/formal_compliant_four_trace_dual")
    parser.add_argument("--artifact", default="outputs/formal_four_trace_representations/trace_representations.json")
    args = parser.parse_args()
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(args.artifact)
    artifact = {item["case_id"]: item["representations"] for item in json.loads(artifact_path.read_text(encoding="utf-8"))}
    result_path = output / "multi_model_results_raw.csv"; prompt_path = output / "multi_model_prompt_log.csv"
    current_results = pd.read_csv(result_path, encoding="utf-8-sig") if result_path.exists() else pd.DataFrame()
    current_prompts = pd.read_csv(prompt_path, encoding="utf-8-sig") if prompt_path.exists() else pd.DataFrame()
    if not current_results.empty:
        generated_event = current_results[current_results["method"] == "spec_rtl_event_abstraction"].copy()
        generated_event_prompts = current_prompts[current_prompts["method"] == "spec_rtl_event_abstraction"].copy()
        if not generated_event.empty:
            generated_event.to_csv(output / "noncanonical_event_partial_results_archived.csv", index=False, encoding="utf-8-sig")
            generated_event_prompts.to_csv(output / "noncanonical_event_partial_prompts_archived.csv", index=False, encoding="utf-8-sig")
            current_results = current_results[current_results["method"] != "spec_rtl_event_abstraction"].copy()
            current_prompts = current_prompts[current_prompts["method"] != "spec_rtl_event_abstraction"].copy()
    complete = set()
    if not current_results.empty:
        counts = current_results.groupby(PROMPT_KEY, dropna=False)["candidate_index"].nunique()
        complete = {tuple(key) for key, count in counts.items() if count >= 2}
    result_additions, prompt_additions, provenance = [], [], {}
    for method, (source_method, representation, source_dir) in REUSE.items():
        source_results_path = source_dir / "multi_model_results_raw.csv"
        source_prompts_path = source_dir / "multi_model_prompt_log.csv"
        source_results = pd.read_csv(source_results_path, encoding="utf-8-sig")
        source_prompts = pd.read_csv(source_prompts_path, encoding="utf-8-sig")
        source_results = source_results[source_results["method"] == source_method].copy()
        source_prompts = source_prompts[source_prompts["method"] == source_method].copy()
        source_results["method"] = method
        source_prompts["method"] = method
        matches = source_prompts.apply(
            lambda row: str(row["trace_representation_text"]).strip() == str(artifact[row["case_id"]][representation]).strip(), axis=1
        )
        if len(source_prompts) != 240 or not bool(matches.all()):
            raise RuntimeError(f"Representation identity failed for {method}: {int(matches.sum())}/{len(matches)}")
        missing_prompt_rows = source_prompts[
            source_prompts.apply(lambda row: tuple(row[col] for col in PROMPT_KEY) not in complete, axis=1)
        ].copy()
        missing_keys = {tuple(row[col] for col in PROMPT_KEY) for _, row in missing_prompt_rows.iterrows()}
        missing_result_rows = source_results[
            source_results.apply(lambda row: tuple(row[col] for col in PROMPT_KEY) in missing_keys, axis=1)
        ].copy()
        result_additions.append(missing_result_rows); prompt_additions.append(missing_prompt_rows)
        provenance[method] = {
            "representation_identity": f"{int(matches.sum())}/{len(matches)}",
            "reused_candidate_rows": len(missing_result_rows), "reused_prompt_cells": len(missing_prompt_rows),
            "source_results_sha256": sha(source_results_path), "source_prompts_sha256": sha(source_prompts_path),
        }
    additions_r = pd.concat(result_additions, ignore_index=True, sort=False)
    additions_p = pd.concat(prompt_additions, ignore_index=True, sort=False)
    merged_r = additions_r if current_results.empty else upsert(current_results, additions_r, KEY)
    merged_p = additions_p if current_prompts.empty else upsert(current_prompts, additions_p, PROMPT_KEY)
    merged_r.to_csv(result_path, index=False, encoding="utf-8-sig")
    merged_p.to_csv(prompt_path, index=False, encoding="utf-8-sig")
    counts = merged_r.groupby(PROMPT_KEY, dropna=False)["candidate_index"].nunique()
    complete_after = int((counts >= 2).sum())
    summary = {
        "schema_version": 1, "policy": "reuse only if trace_representation_text exactly equals the fixed compliant artifact",
        "event_abstraction_reused": True, "event_reuse_reason": "240/240 exact canonical prompt representation identity; noncanonical partial event results archived and excluded",
        "artifact_sha256": sha(artifact_path), "complete_cells_after_reuse": complete_after,
        "remaining_cells": 960 - complete_after, "remaining_candidates": 2 * (960 - complete_after), "sources": provenance,
    }
    (output / "arm_reuse_provenance.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__": main()
