from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from run_trace_abstraction_prototype import run_case_eval


ROOT = Path(__file__).resolve().parents[1]
TOP1 = ROOT / "outputs/behavioral_preference_pilot_v1/frozen_top1_v1"
MANIFEST = TOP1 / "query_manifest.json"
DEFINITIONS = TOP1 / "frozen_metric_definitions_v1.json"
OUT = TOP1 / "execution_evaluation_v1"
EXPECTED_MANIFEST_SHA256 = "4b57a42c1d06d7ea8a967cd7753ca610368f21698e21564c075a02c4fbafe4ec"
METHODS = (
    "ordinary_sft",
    "pass_count_dpo",
    "scalar_score_dpo",
    "random_probe_dominance_dpo",
    "full_disagreement_dominance_dpo",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def visible_signals(case_dir: Path) -> list[str]:
    waveform = case_dir / "waveform_good.csv"
    if waveform.is_file():
        with waveform.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
        return list(dict.fromkeys(x.split("[", 1)[0].strip() for x in header if x.strip() != "time_ps"))
    # The frozen query builder used testbench-top declarations as its interface.
    import re
    clean = re.sub(r"//.*?$|/\*.*?\*/", "", (case_dir / "tb.v").read_text(encoding="utf-8"), flags=re.M | re.S)
    out: list[str] = []
    for match in re.finditer(r"\b(?:reg|wire|logic)\b([^;]*);", clean):
        declaration = re.sub(r"\[[^\]]+\]", " ", match.group(1))
        declaration = re.sub(r"\b(?:signed|unsigned)\b", " ", declaration)
        for item in declaration.split(","):
            found = re.search(r"([A-Za-z_]\w*)\s*$", item.split("=", 1)[0].strip())
            if found:
                out.append(found.group(1))
    return list(dict.fromkeys(out))


def false_result(reason: str) -> dict:
    return {
        "compile_ok": False, "correct_pass": False, "buggy_fail": False,
        "antecedent_hit": False, "non_vacuous": False,
        "heldout_correct_pass": False, "heldout_buggy_fail": False,
        "heldout_antecedent_hit": False, "heldout_non_vacuous": False,
        "trace_overfit": False, "evaluation_error": reason,
        "compile_duration_sec": 0.0, "verification_duration_sec": 0.0,
    }


def primitive_bools(result: dict) -> dict:
    keys = (
        "compile_ok", "correct_pass", "buggy_fail", "antecedent_hit", "non_vacuous",
        "heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit",
        "heldout_non_vacuous", "trace_overfit",
    )
    return {key: bool(result.get(key, False)) for key in keys}


def derived(result: dict) -> dict:
    b = primitive_bools(result)
    primary = b["compile_ok"] and b["correct_pass"] and b["buggy_fail"]
    strict = primary and b["antecedent_hit"] and b["non_vacuous"] \
        and b["heldout_correct_pass"] and b["heldout_buggy_fail"] \
        and b["heldout_antecedent_hit"] and b["heldout_non_vacuous"]
    return {
        "primary_success": primary,
        "strict_success": strict,
        "fixed_safe": b["correct_pass"] and b["heldout_correct_pass"],
        "target_detect": b["buggy_fail"] and b["heldout_buggy_fail"],
        "non_vacuity_metric": b["antecedent_hit"] and b["heldout_antecedent_hit"],
    }


def tool_version(command: list[str]) -> str:
    try:
        p = subprocess.run(command, capture_output=True, timeout=30)
        output = (p.stdout or b"") + (p.stderr or b"")
        lines = output.decode("utf-8", errors="replace").strip().splitlines()
        return lines[0] if lines else f"exit={p.returncode}; no version text"
    except Exception as exc:
        return f"unavailable: {exc}"


def preflight() -> tuple[dict, list[dict]]:
    if sha(MANIFEST) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("frozen query manifest hash mismatch")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = manifest["records"]
    if len(records) != 48:
        raise RuntimeError(f"expected 48 queries, found {len(records)}")
    problems: list[str] = []
    adapter_hashes: dict[str, set[str]] = defaultdict(set)
    for method in METHODS:
        for record in records:
            case_id = record["case_id"]
            evidence = TOP1 / "generations" / method / case_id / "evidence.json"
            raw = evidence.parent / "raw_response.txt"
            candidate = evidence.parent / "candidate.sva"
            if not evidence.is_file() or not raw.is_file() or not candidate.is_file():
                problems.append(f"missing artifact: {method}/{case_id}")
                continue
            doc = json.loads(evidence.read_text(encoding="utf-8"))
            if doc.get("status") != "complete" or doc.get("prompt_sha256") != record["prompt_sha256"]:
                problems.append(f"evidence mismatch: {method}/{case_id}")
            if sha(raw) != doc.get("raw_response_sha256") or sha(candidate) != doc.get("candidate_sva_sha256"):
                problems.append(f"generation hash mismatch: {method}/{case_id}")
            adapter_hashes[method].add(doc.get("adapter_sha256", ""))
    if problems:
        raise RuntimeError("; ".join(problems[:10]))
    if any(len(adapter_hashes[m]) != 1 for m in METHODS):
        raise RuntimeError("expected one adapter hash per method")
    audit = {
        "status": "pass", "query_manifest_sha256": sha(MANIFEST),
        "metric_definitions_sha256": sha(DEFINITIONS), "query_count": 48,
        "method_count": 5, "generation_count": 240,
        "adapter_hashes": {m: next(iter(adapter_hashes[m])) for m in METHODS},
        "deletion_policy": "all 240 frozen Top-1 records retained in denominators",
        "heldout_outcomes_used_for_generation": False,
        "tool_versions": {
            "python": sys.version.split()[0],
            "wsl_iverilog": tool_version(["wsl", "bash", "-lc", "iverilog -V 2>&1 | grep -m1 'Icarus Verilog version'"]),
            "wsl_vvp": tool_version(["wsl", "bash", "-lc", "vvp -V 2>&1 | grep -m1 'Icarus Verilog runtime version'"]),
        },
    }
    return audit, records


def summarize(rows: list[dict], split: str) -> dict:
    selected = rows if split == "union_overview" else [r for r in rows if split in r["memberships"]]
    by_method: dict[str, dict] = {}
    for method in METHODS:
        group = [r for r in selected if r["method"] == method]
        n = len(group)
        if not n:
            raise RuntimeError(f"no rows for {method}/{split}")
        families = {r["bug_family"] for r in group}
        recalled = {r["bug_family"] for r in group if r["strict_success"]}
        primary_count = sum(r["primary_success"] for r in group)
        trace_overfit_count = sum(r["trace_overfit"] for r in group)
        by_method[method] = {
            "query_count": n,
            "compile_rate": sum(r["compile_ok"] for r in group) / n,
            "SCS@1": sum(r["strict_success"] for r in group) / n,
            "Fixed-Safe": sum(r["fixed_safe"] for r in group) / n,
            "Target Detect": sum(r["target_detect"] for r in group) / n,
            "Family Recall": len(recalled) / len(families),
            "Non-vacuity": sum(r["non_vacuity_metric"] for r in group) / n,
            "TOR": trace_overfit_count / primary_count if primary_count else None,
            "counts": {
                "strict_success": sum(r["strict_success"] for r in group),
                "fixed_safe": sum(r["fixed_safe"] for r in group),
                "target_detect": sum(r["target_detect"] for r in group),
                "recalled_families": len(recalled), "test_families": len(families),
                "non_vacuous": sum(r["non_vacuity_metric"] for r in group),
                "primary_success": primary_count, "trace_overfit": trace_overfit_count,
            },
        }
    return {"split": split, "methods": by_method}


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
    record_map = {r["case_id"]: r for r in records}
    evidence_dir = OUT / "records"
    command = "python3 src/evaluate_frozen_top1_v1.py --resume"
    start = time.perf_counter()
    for method in METHODS:
        for index, record in enumerate(records, 1):
            case_id = record["case_id"]
            out_path = evidence_dir / method / case_id / "evaluation.json"
            if args.resume and out_path.is_file():
                continue
            generation_dir = TOP1 / "generations" / method / case_id
            generation = json.loads((generation_dir / "evidence.json").read_text(encoding="utf-8"))
            candidate_path = generation_dir / "candidate.sva"
            candidate = candidate_path.read_text(encoding="utf-8").strip()
            case_dir = ROOT / record["dataset_root"] / case_id
            item_started = time.perf_counter()
            if not generation.get("sva_extracted", False) or not candidate:
                result = false_result("frozen_top1_extraction_failure")
            else:
                try:
                    result = run_case_eval(
                        case_id=case_id, assertion_text=candidate,
                        signal_names=visible_signals(case_dir), use_property=False,
                        runtime_dir=OUT / "runtime" / method / case_id,
                        cases_root=case_dir.parent,
                    )
                except Exception as exc:
                    result = false_result(f"evaluation_exception: {type(exc).__name__}: {exc}")
            row = {
                "status": "complete", "method": method, "query_id": record["query_id"],
                "case_id": case_id, "parent_bug_id": record["parent_bug_id"],
                "bug_family": record["bug_family"], "memberships": record["memberships"],
                "prompt_sha256": record["prompt_sha256"],
                "adapter_sha256": generation["adapter_sha256"],
                "raw_response_sha256": generation["raw_response_sha256"],
                "candidate_sva_sha256": generation["candidate_sva_sha256"],
                "sva_extracted": bool(generation.get("sva_extracted", False)),
                "evaluation_command": command,
                **primitive_bools(result), **derived(result),
                "evaluation_error": result.get("evaluation_error"),
                "compile_duration_sec": result.get("compile_duration_sec", 0.0),
                "verification_duration_sec": result.get("verification_duration_sec", 0.0),
                "wall_clock_seconds": time.perf_counter() - item_started,
                "raw_evaluation": result,
            }
            dump(out_path, row)
            print(f"[{method} {index}/48] {case_id} compile={row['compile_ok']} strict={row['strict_success']}", flush=True)
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(evidence_dir.rglob("evaluation.json"))]
    if len(rows) != 240:
        raise RuntimeError(f"expected 240 evaluation rows, found {len(rows)}")
    summaries = {split: summarize(rows, split) for split in ("unseen_parent", "unseen_bug_family", "union_overview")}
    result = {
        "status": "complete", "metric_definitions_sha256": sha(DEFINITIONS),
        "query_manifest_sha256": sha(MANIFEST), "record_count": len(rows),
        "project_ood": "N/A", "summaries": summaries,
        "wall_clock_seconds": time.perf_counter() - start,
    }
    dump(OUT / "frozen_top1_metrics.json", result)
    hashes = {}
    for path in sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "evaluation_artifact_hashes.json"):
        hashes[str(path.relative_to(ROOT)).replace("\\", "/")] = sha(path)
    dump(OUT / "evaluation_artifact_hashes.json", hashes)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
