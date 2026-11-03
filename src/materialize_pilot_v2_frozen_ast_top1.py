from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import materialize_frozen_top1_queries as v1

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "outputs/behavioral_preference_pilot_v1/frozen_top1_v1"
V2 = ROOT / "outputs/behavioral_preference_pilot_v2"
OUT = V2 / "frozen_top1_ast_v2"
FORBIDDEN = ("heldout", "held-out", "fp set", "tp set", "test outcome", "target_detect", "fixed_safe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clock_reset(signals: list[str]):
    clock = next((x for x in ("clk_i", "clk", "clock", "i_clk") if x in signals), None)
    reset = next((x for x in ("rst_ni", "rst_n", "reset_n", "aresetn", "rst", "reset") if x in signals), None)
    return clock, reset


def main() -> None:
    manifest_path = OUT / "query_manifest.json"
    if manifest_path.exists():
        raise RuntimeError("refusing to overwrite frozen_top1_ast_v2 manifest")
    old_path = V1 / "query_manifest.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    if old["query_count"] != 48:
        raise RuntimeError("unexpected frozen v1 query universe")
    records = []
    for row in old["records"]:
        case = ROOT / row["dataset_root"] / row["case_id"]
        spec = ROOT / row["spec_path"]
        rtl, tb = case / "correct.v", case / "tb.v"
        signals = v1.visible(tb.read_text(encoding="utf-8"))
        clock, reset = clock_reset(signals)
        semantic = [x for x in signals if x not in {clock, reset}]
        if not semantic:
            raise RuntimeError(f"no semantic visible signals: {row['case_id']}")
        prompt = (
            "Return exactly one compact JSON object, then EOS. Output no prose, markdown, metadata, or SystemVerilog.\n"
            'Keys in this exact order: "antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation".\n'
            f"antecedent_signal and consequent_signal must be one of: {', '.join(semantic)}.\n"
            'antecedent_polarity must be "high" or "low". implication must be "|->" or "|=>". '
            'relation must be "high", "low", "equal", or "not_equal".\n'
            "The object must contain exactly the five declared keys; extra keys are invalid.\n"
            f"Case: {row['case_id']}\nProject: {row['source_project']}\nModule: {row['source_module']}\n"
            f"Bug family: {row['bug_family']}\nSpecification:\n{spec.read_text(encoding='utf-8')}\n\n"
            f"Correct RTL:\n{rtl.read_text(encoding='utf-8')}\n"
        )
        hits = [term for term in FORBIDDEN if term in prompt.lower()]
        if hits:
            raise RuntimeError(f"outcome-like prompt term in {row['case_id']}: {hits}")
        query_dir = OUT / "queries" / row["case_id"]
        query_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = query_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        records.append({
            **row,
            "query_id": hashlib.sha256(("frozen_top1_ast_v2\0" + row["case_id"]).encode()).hexdigest()[:24],
            "prompt_path": str(prompt_path.relative_to(ROOT)).replace("\\", "/"),
            "prompt_sha256": sha(prompt_path),
            "visible_signals": signals,
            "semantic_signals": semantic,
            "clock": clock,
            "reset": reset,
        })
    manifest = {
        "status": "frozen_before_any_top1_generation",
        "version": "frozen_top1_ast_v2_strict_trie_eos",
        "source_query_manifest_sha256": sha(old_path),
        "test_universe_unchanged": True,
        "query_count": 48,
        "split_counts": old["split_counts"],
        "strict_group_counts": old["strict_group_counts"],
        "project_ood": old["project_ood"],
        "decode": {"temperature": 0.0, "do_sample": False, "num_return_sequences": 1, "max_new_tokens": 128,
                   "reranker": False, "repair": False, "selector": False, "heldout_information": False,
                   "constraint": "complete schema-valid canonical JSON trie; closing brace followed by forced EOS"},
        "records": sorted(records, key=lambda x: x["query_id"]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    audit = {
        "status": "pass",
        "query_manifest_sha256": sha(manifest_path),
        "source_query_manifest_sha256": sha(old_path),
        "same_48_case_ids": {x["case_id"] for x in records} == {x["case_id"] for x in old["records"]},
        "same_memberships": all(next(x for x in old["records"] if x["case_id"] == r["case_id"])["memberships"] == r["memberships"] for r in records),
        "prompt_forbidden_term_hits": 0,
        "buggy_rtl_in_model_input": False,
        "fp_tp_in_model_input": False,
        "outcome_fields_in_model_input": False,
    }
    (OUT / "pre_generation_leakage_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "query_count": 48, "manifest_sha256": sha(manifest_path), "audit": audit}, sort_keys=True))


if __name__ == "__main__":
    main()
