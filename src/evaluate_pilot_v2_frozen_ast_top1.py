from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from evaluate_frozen_top1_v1 import (
    METHODS,
    derived,
    false_result,
    primitive_bools,
    run_case_eval,
    summarize,
    tool_version,
    visible_signals,
)

ROOT = Path(__file__).resolve().parents[1]
TOP1 = ROOT / "outputs/behavioral_preference_pilot_v2/frozen_top1_ast_v2"
MANIFEST = TOP1 / "query_manifest.json"
DEFINITIONS = ROOT / "outputs/behavioral_preference_pilot_v1/frozen_top1_v1/frozen_metric_definitions_v1.json"
OUT = TOP1 / "execution_evaluation_v1"
EXPECTED_MANIFEST_SHA256 = "137a58c4b891ff7df1104ac73a7c0e42d39fd3bc856af90c8958fbfcf9fd8aa3"
KEYS = ("antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation")


def sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render(ast: dict, clock: str | None, reset: str | None) -> str:
    ant_signal = ast["antecedent_signal"]
    ant = ant_signal if ast["antecedent_polarity"] == "high" else f"!{ant_signal}"
    cons_signal = ast["consequent_signal"]
    cons = {
        "high": cons_signal,
        "low": f"!{cons_signal}",
        "equal": f"({cons_signal} == {ant_signal})",
        "not_equal": f"({cons_signal} != {ant_signal})",
    }[ast["relation"]]
    event = f"posedge {clock}" if clock else f"{ant_signal} or {cons_signal}"
    disable = ""
    if reset:
        active = f"!{reset}" if reset.endswith(("_n", "_ni", "n")) else reset
        disable = f" disable iff ({active})"
    return f"assert property (@({event}){disable} ({ant}) {ast['implication']} ({cons}));"


def preflight():
    if sha(MANIFEST) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("frozen AST Top-1 manifest hash mismatch")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = manifest["records"]
    if len(records) != 48 or not manifest.get("test_universe_unchanged"):
        raise RuntimeError("unexpected frozen test universe")
    problems = []
    adapters = {}
    for method in METHODS:
        hashes = set()
        for record in records:
            directory = TOP1 / "generations" / method / record["case_id"]
            evidence_path, raw_path, ast_path = directory / "evidence.json", directory / "raw_response.txt", directory / "ast.json"
            if not all(path.is_file() for path in (evidence_path, raw_path, ast_path)):
                problems.append(f"missing artifact {method}/{record['case_id']}")
                continue
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            ast = json.loads(ast_path.read_text(encoding="utf-8"))
            valid = (
                evidence.get("status") == "complete"
                and evidence.get("prompt_sha256") == record["prompt_sha256"]
                and evidence.get("schema_keys_valid") is True
                and evidence.get("ended_on_eos") is True
                and evidence.get("hit_max_new_tokens") is False
                and evidence.get("generation_constraint") == "strict_schema_trie"
                and tuple(ast) == KEYS
                and sha(raw_path) == evidence.get("raw_response_sha256")
                and sha(ast_path) == evidence.get("ast_sha256")
            )
            if not valid:
                problems.append(f"generation mismatch {method}/{record['case_id']}")
            hashes.add(evidence.get("adapter_sha256"))
        if len(hashes) != 1:
            problems.append(f"adapter hash count {method}={len(hashes)}")
        else:
            adapters[method] = next(iter(hashes))
    if problems:
        raise RuntimeError("; ".join(problems[:10]))
    audit = {
        "status": "pass",
        "query_manifest_sha256": sha(MANIFEST),
        "source_v1_query_manifest_sha256": manifest["source_query_manifest_sha256"],
        "metric_definitions_sha256": sha(DEFINITIONS),
        "query_count": 48,
        "method_count": 5,
        "generation_count": 240,
        "adapter_hashes": adapters,
        "deletion_policy": "all 240 one-shot records retained in denominators; render/compile failures score false",
        "heldout_outcomes_used_for_generation": False,
        "repair": False,
        "reranker": False,
        "selector": False,
        "tool_versions": {
            "python": sys.version.split()[0],
            "wsl_iverilog": tool_version(["wsl", "bash", "-lc", "iverilog -V 2>&1 | grep -m1 'Icarus Verilog version'"]),
            "wsl_vvp": tool_version(["wsl", "bash", "-lc", "vvp -V 2>&1 | grep -m1 'Icarus Verilog runtime version'"]),
        },
    }
    return audit, records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    audit, records = preflight()
    OUT.mkdir(parents=True, exist_ok=True)
    dump(OUT / "pre_execution_audit.json", audit)
    if args.preflight_only:
        print(json.dumps(audit, sort_keys=True))
        return
    began = time.perf_counter()
    for method in METHODS:
        for index, record in enumerate(records, 1):
            case_id = record["case_id"]
            output = OUT / "records" / method / case_id / "evaluation.json"
            if args.resume and output.is_file():
                continue
            generation_dir = TOP1 / "generations" / method / case_id
            generation = json.loads((generation_dir / "evidence.json").read_text(encoding="utf-8"))
            ast_path = generation_dir / "ast.json"
            ast = json.loads(ast_path.read_text(encoding="utf-8"))
            candidate = render(ast, record.get("clock"), record.get("reset"))
            rendered = OUT / "rendered" / method / case_id / "candidate.sva"
            rendered.parent.mkdir(parents=True, exist_ok=True)
            rendered.write_text(candidate + "\n", encoding="utf-8")
            case_dir = ROOT / record["dataset_root"] / case_id
            item_started = time.perf_counter()
            try:
                result = run_case_eval(
                    case_id=case_id,
                    assertion_text=candidate,
                    signal_names=visible_signals(case_dir),
                    use_property=False,
                    runtime_dir=OUT / "runtime" / method / case_id,
                    cases_root=case_dir.parent,
                )
            except Exception as exc:
                result = false_result(f"evaluation_exception: {type(exc).__name__}: {exc}")
            row = {
                "status": "complete", "method": method, "query_id": record["query_id"], "case_id": case_id,
                "parent_bug_id": record["parent_bug_id"], "bug_family": record["bug_family"], "memberships": record["memberships"],
                "prompt_sha256": record["prompt_sha256"], "adapter_sha256": generation["adapter_sha256"],
                "raw_response_sha256": generation["raw_response_sha256"], "ast_sha256": generation["ast_sha256"],
                "candidate_sva_sha256": sha(rendered), "rendered_candidate_path": str(rendered.relative_to(ROOT)).replace("\\", "/"),
                "evaluation_command": "python3 src/evaluate_pilot_v2_frozen_ast_top1.py --resume",
                **primitive_bools(result), **derived(result), "evaluation_error": result.get("evaluation_error"),
                "compile_duration_sec": result.get("compile_duration_sec", 0.0),
                "verification_duration_sec": result.get("verification_duration_sec", 0.0),
                "wall_clock_seconds": time.perf_counter() - item_started, "raw_evaluation": result,
            }
            dump(output, row)
            print(f"[{method} {index}/48] {case_id} compile={row['compile_ok']} strict={row['strict_success']}", flush=True)
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((OUT / "records").rglob("evaluation.json"))]
    if len(rows) != 240:
        raise RuntimeError(f"expected 240 evaluation rows, found {len(rows)}")
    summaries = {split: summarize(rows, split) for split in ("unseen_parent", "unseen_bug_family", "union_overview")}
    result = {
        "status": "complete", "metric_definitions_sha256": sha(DEFINITIONS), "query_manifest_sha256": sha(MANIFEST),
        "record_count": 240, "project_ood": "N/A", "summaries": summaries,
        "wall_clock_seconds": time.perf_counter() - began,
    }
    dump(OUT / "frozen_top1_metrics.json", result)
    hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path) for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "evaluation_artifact_hashes.json"}
    dump(OUT / "evaluation_artifact_hashes.json", hashes)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
