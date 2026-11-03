#!/usr/bin/env python3
"""Read-only Phase-B lineage audit; never imports or invokes a trainer."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables/phase_b_lineage_edge_audit_20260921"
RAW = OUT / "raw"
V1 = Path("outputs/behavioral_preference_pilot_v1")
V2 = Path("outputs/behavioral_preference_pilot_v2")
CORPUS = V2 / "training_corpora_v2"
BALANCED = V2 / "balanced_behavioral_objective_v1"
PHASE = BALANCED / "phase_b_refit_all30_v1"
SCHEDULE = PHASE / "anchor_20_all30.jsonl"
DOMINANCE = V1 / "dominance_pairs_v3/disagreement_guided_dominance_pairs.jsonl"
CORPUS_PAIRS = CORPUS / "full_disagreement_dominance_dpo.jsonl"
EDGES = BALANCED / "dpo_edges_all30.jsonl"
ANCHORS = BALANCED / "safe_detect_anchors_all30.jsonl"
KEYS = ("antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> None:
    if OUT.exists():
        prior = OUT / "summary.json"
        if not prior.is_file() or read_json(prior).get("status") != "AUDIT_COMPLETE_EXECUTION_UNVERIFIABLE":
            raise RuntimeError(f"Refusing to replace unrecognized audit output: {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    inventory: list[dict] = []

    def preserve(path_text: str, role: str, expected_hash: str | None = None) -> dict:
        source = ROOT / path_text
        record = {"role": role, "source_path": path_text, "absolute_source_path": str(source),
                  "copy_path": "", "status": "MISSING", "bytes": "", "sha256": "",
                  "expected_sha256": expected_hash or "", "hash_match": ""}
        if source.is_file():
            dest = RAW / path_text
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            source_hash, copied_hash = sha(source), sha(dest)
            if source_hash != copied_hash:
                raise RuntimeError(f"Evidence copy changed bytes: {path_text}")
            record.update({"copy_path": rel(dest), "status": "FOUND", "bytes": source.stat().st_size,
                           "sha256": source_hash, "hash_match": "NOT_DECLARED" if expected_hash is None
                           else str(source_hash == expected_hash).upper()})
        inventory.append(record)
        return record

    schedule_lines = (ROOT / SCHEDULE).read_bytes().splitlines(keepends=True)
    schedule = read_jsonl(ROOT / SCHEDULE)
    if len(schedule_lines) != len(schedule):
        raise RuntimeError("Schedule physical lines differ from parsed rows")
    dominance = {x["pair_id"]: x for x in read_jsonl(ROOT / DOMINANCE)}
    corpus_pairs = {x["pair_id"]: x for x in read_jsonl(ROOT / CORPUS_PAIRS)}
    edge_pool = {x["pair_id"]: x for x in read_jsonl(ROOT / EDGES)}
    anchor_pool = {x["example_id"]: x for x in read_jsonl(ROOT / ANCHORS)}
    corpus_hashes = read_json(ROOT / CORPUS / "SHA256SUMS.json")
    frozen = read_json(ROOT / PHASE / "phase_b_refit_all30_v1_frozen.json")
    source_paths = [
        (DOMINANCE, "preference_pairs"), (CORPUS_PAIRS, "canonical_pair_index"),
        (EDGES, "phase_b_edge_pool"), (ANCHORS, "phase_b_anchor_pool"),
        (SCHEDULE, "ordered_schedule"), (PHASE / "phase_b_refit_all30_v1_frozen.json", "schedule_freeze"),
        (PHASE / "SHA256SUMS.json", "schedule_hash_manifest"),
        (CORPUS / "SHA256SUMS.json", "canonical_text_hash_manifest"),
        (CORPUS / "formal_training_v2_frozen.json", "canonical_protocol"),
        (BALANCED / "balanced_behavioral_objective_v1_frozen.json", "objective_freeze"),
        (BALANCED / "dev_top1_v1/execution_evaluation_v1/dev_metrics_and_selection.json", "dev_selection"),
        (V2 / "balanced_behavioral_objective_v1/phase_b_refit_all30_v1/frozen_ood_top1_v1/query_manifest.json", "evaluation_load_binding"),
        (V2 / "balanced_behavioral_objective_v1/phase_b_refit_all30_v1/frozen_ood_top1_v1/generation_run_manifest.json", "generation_run_claim"),
        (Path("outputs/phase_b_ood_eval_v1/pre_execution_audit.json"), "evaluation_preflight"),
        (Path("outputs/checkpoints/Qwen3-8B/checkpoint_manifest.json"), "base_checkpoint_manifest"),
    ]
    code_paths = [
        "src/materialize_pilot_v2_corrected_protocol.py",
        "src/freeze_and_materialize_balanced_behavioral_objective.py",
        "src/materialize_balanced_behavioral_phase_b.py",
        "src/materialize_balanced_behavioral_token_schedules.py",
        "src/train_balanced_behavioral_phase_b_qwen3.py",
        "src/train_balanced_behavioral_dev_qwen3.py",
        "src/generate_balanced_behavioral_phase_b_ood.py",
        "src/evaluate_balanced_behavioral_phase_b_ood.py",
        "scripts/run_balanced_behavioral_phase_b_training_v1.sh",
    ]
    for path, role in source_paths:
        preserve(path.as_posix(), role, frozen["schedule_sha256"] if path == SCHEDULE else None)
    for path in code_paths:
        preserve(path, "lineage_script")

    text_paths = sorted({row[field] for row in schedule for field in
                         ("prompt_path", "response_path", "chosen_path", "rejected_path") if row.get(field)})
    text_info: dict[str, dict] = {}
    for path in text_paths:
        text_info[path] = preserve(path, "exact_trainer_text", corpus_hashes.get(path))

    candidate_ids = sorted({row[field] for row in schedule for field in
                            ("example_id", "chosen_id", "rejected_id") if row.get(field)})
    candidate_checks: list[dict] = []
    for cid in candidate_ids:
        parent, slot = cid.rsplit("__v3_slot_", 1)
        prefix = V1 / "sequential_generation_v3_pilot30" / parent / f"slot_{slot}" / "attempt_01"
        evidence_path = prefix / "evidence.json"
        evidence = read_json(ROOT / evidence_path)
        for name in ("evidence.json", "raw_response.json", "prompt.txt", "candidate.sva", "request.json"):
            preserve((prefix / name).as_posix(), "original_candidate_" + name)
        response_path = (CORPUS / "responses" / f"{cid}.json").as_posix()
        response = (ROOT / response_path).read_bytes()
        ast = json.loads(response)
        canonical = json.dumps({key: evidence["ast"][key] for key in KEYS},
                               ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        candidate_checks.append({"candidate_id": cid, "parent_bug_id": parent, "slot": int(slot),
                                 "provenance_class": "SYNTHETIC_CONTROL" if int(slot) == 8 else "NATURAL_RENDERED",
                                 "generation_evidence_path": evidence_path.as_posix(),
                                 "generation_evidence_sha256": sha(ROOT / evidence_path),
                                 "original_raw_response_path": (prefix / "raw_response.json").as_posix(),
                                 "original_raw_response_sha256": sha(ROOT / prefix / "raw_response.json"),
                                 "canonical_response_path": response_path,
                                 "canonical_response_sha256": sha_bytes(response),
                                 "canonical_five_keys": tuple(ast) == KEYS,
                                 "canonical_matches_generation_ast": response == canonical,
                                 "generation_raw_hash_declared_matches": evidence.get("raw_response_sha256") == sha(ROOT / prefix / "raw_response.json")})
    check_by_id = {x["candidate_id"]: x for x in candidate_checks}

    edge_rows: list[dict] = []
    failures = Counter()
    for step, row in enumerate(schedule, 1):
        kind = row["record_type"]
        base = {"schedule_step": step, "schedule_line_sha256": sha_bytes(schedule_lines[step - 1]),
                "record_type": kind, "record_id": row.get("pair_id", row.get("example_id")),
                "parent_bug_id": row["parent_bug_id"], "objective_bucket": row["objective_bucket"],
                "loss_tokens_declared": row["loss_tokens"], "prompt_path": row["prompt_path"],
                "prompt_sha256": text_info[row["prompt_path"]]["sha256"],
                "chosen_or_response_path": row.get("chosen_path", row.get("response_path")),
                "chosen_or_response_sha256": text_info[row.get("chosen_path", row.get("response_path"))]["sha256"],
                "rejected_path": row.get("rejected_path", ""),
                "rejected_sha256": text_info[row["rejected_path"]]["sha256"] if row.get("rejected_path") else "",
                "source_preference_pair_id": "", "source_pair_sha256_declared": "",
                "source_pair_sha256_recomputed": "", "source_link_status": "", "provenance_class": "",
                "trainer_read_location": "src/train_balanced_behavioral_dev_qwen3.py:main; rows=schedule[step]; read_text(prompt/response or chosen/rejected)",
                "observed_execution_status": "UNVERIFIABLE_MISSING_TRAIN_LOG_AND_CHECKPOINT"}
        if kind == "dpo_edge":
            pid = row["pair_id"]
            source, corpus, pool = dominance.get(pid), corpus_pairs.get(pid), edge_pool.get(pid)
            base["source_preference_pair_id"] = pid
            base["source_pair_sha256_declared"] = row["source_pair_sha256"]
            if source is not None:
                base["source_pair_sha256_recomputed"] = sha_bytes(json.dumps(source, sort_keys=True).encode())
            checks = {
                "dominance_pair_found": source is not None,
                "canonical_pair_index_found": corpus is not None,
                "phase_b_edge_pool_found": pool is not None,
                "chosen_rejected_ids_match": bool(source and corpus and pool and
                   all(x["chosen_id"] == row["chosen_id"] and x["rejected_id"] == row["rejected_id"]
                       for x in (source, corpus, pool))),
                "canonical_paths_match": bool(corpus and all(corpus[k] == row[k]
                    for k in ("prompt_path", "chosen_path", "rejected_path"))),
                "phase_b_pool_fields_match": bool(pool and all(pool.get(k) == row.get(k)
                    for k in pool if k not in ("loss_tokens", "objective_bucket", "schedule_cycle", "schedule_section"))),
                "source_pair_hash_match": bool(source and base["source_pair_sha256_recomputed"] == row["source_pair_sha256"]),
            }
            base["provenance_class"] = "MIXED_SYNTHETIC_CONTROL" if any(
                check_by_id[x]["slot"] == 8 for x in (row["chosen_id"], row["rejected_id"])) else "NATURAL_ONLY"
        elif kind == "sft_anchor":
            cid = row["example_id"]
            pool = anchor_pool.get(cid)
            checks = {"anchor_pool_found": pool is not None,
                      "anchor_pool_fields_match": bool(pool and all(pool.get(k) == row.get(k)
                          for k in pool if k not in ("loss_tokens", "objective_bucket", "schedule_cycle", "schedule_section"))),
                      "canonical_response_matches_generation_ast": check_by_id[cid]["canonical_matches_generation_ast"]}
            base["provenance_class"] = "SYNTHETIC_CONTROL" if check_by_id[cid]["slot"] == 8 else "NATURAL_ONLY"
        else:
            raise RuntimeError(f"Unexpected schedule row type at step {step}: {kind}")
        bad = [name for name, passed in checks.items() if not passed]
        failures.update(bad)
        base["source_link_status"] = "PASS" if not bad else "FAIL:" + ",".join(bad)
        edge_rows.append(base)

    run_log_paths = sorted({p for pattern in (
        "*training*.log", "*training*resume*.log", "*phase_b_ood_evaluation*.log")
        for p in ROOT.glob(pattern) if p.is_file()})
    for path in run_log_paths:
        preserve(rel(path), "existing_launcher_or_evaluation_log_not_phase_b_trainer_log")
    required_missing = [
        PHASE / "formal_training_v1/anchor_20_all30/train_log.jsonl",
        PHASE / "formal_training_v1/anchor_20_all30/training_result.json",
        PHASE / "formal_training_v1/anchor_20_all30/latest_checkpoint.txt",
        PHASE / "formal_training_v1/anchor_20_all30/checkpoint-004058/adapter_model.safetensors",
        PHASE / "formal_training_v1/anchor_20_all30/checkpoint-004058/state.json",
    ]
    for path in required_missing:
        preserve(path.as_posix(), "required_execution_or_adapter_evidence")

    write_csv(OUT / "artifact_inventory.csv", inventory, list(inventory[0]))
    write_csv(OUT / "candidate_response_lineage.csv", candidate_checks, list(candidate_checks[0]))
    write_csv(OUT / "schedule_edge_lineage.csv", edge_rows, list(edge_rows[0]))
    summary = {
        "status": "AUDIT_COMPLETE_EXECUTION_UNVERIFIABLE",
        "schedule_path": SCHEDULE.as_posix(), "schedule_sha256": sha(ROOT / SCHEDULE),
        "schedule_rows": len(schedule), "unique_trainer_text_files": len(text_paths),
        "all_text_files_present": all(text_info[x]["status"] == "FOUND" for x in text_paths),
        "all_text_hashes_match_declared_corpus_manifest": all(text_info[x]["hash_match"] == "TRUE" for x in text_paths),
        "unique_source_candidates": len(candidate_checks),
        "all_canonical_responses_match_generation_ast": all(x["canonical_matches_generation_ast"] for x in candidate_checks),
        "source_link_failures": dict(failures), "source_link_pass_rows": sum(x["source_link_status"] == "PASS" for x in edge_rows),
        "provenance_rows": dict(Counter(x["provenance_class"] for x in edge_rows)),
        "loss_tokens_declared_sum": sum(x["loss_tokens"] for x in schedule),
        "existing_nontrainer_log_files_copied": len(run_log_paths),
        "missing_required_execution_artifacts": [x.as_posix() for x in required_missing if not (ROOT / x).is_file()],
        "execution_conclusion": "Ordered schedule and trainer read path are verified as code/data. No original Phase-B train log, training result, or adapter bytes exist in this checkout; 4058 executed optimizer steps and the historical model load cannot be independently proven.",
    }
    write_json(OUT / "summary.json", summary)
    # Inventory is non-recursive with respect to its own hash manifest.
    output_hashes = [{"path": rel(p), "bytes": p.stat().st_size, "sha256": sha(p)}
                     for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "SHA256SUMS.csv"]
    write_csv(OUT / "SHA256SUMS.csv", output_hashes, ["path", "bytes", "sha256"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
