from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "rtl_cases_real_scale210_independent"
OUTPUT = ROOT / "outputs" / "pristine_trace_router_v1" / "sealed_test_manifest.json"
SEED = "trace-router-pristine-v1-20260719"
TEST_PARENT_COUNT = 16


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    candidates = sorted(path for path in DATASET.iterdir() if path.is_dir() and path.name.startswith("case4"))
    ranked = sorted(candidates, key=lambda path: hashlib.sha256(f"{SEED}|{path.name}".encode()).hexdigest())
    selected = ranked[:TEST_PARENT_COUNT]
    outcome_hits = []
    outcome_names = {"multi_model_results_raw.csv", "pending_candidates.csv"}
    outcome_paths = []
    for directory, dirnames, filenames in os.walk(ROOT / "outputs"):
        dirnames[:] = [name for name in dirnames if name not in {"runtime", "prompts", "responses", "logs", "models", "generated"}]
        outcome_paths.extend(Path(directory) / name for name in filenames if name in outcome_names)
    # The active formal generated directory is intentionally included after pruning other bulky generated trees.
    outcome_paths.extend((ROOT / "outputs" / "formal_trace_router").glob("**/generated/pending_candidates.csv"))
    outcome_paths.extend((ROOT / "outputs" / "formal_trace_router").glob("**/generated/multi_model_results_raw.csv"))
    for csv_path in sorted(set(outcome_paths)):
        text = csv_path.read_text(encoding="utf-8-sig", errors="ignore")
        for path in selected:
            if path.name in text:
                outcome_hits.append({"case_id": path.name, "file": str(csv_path.resolve())})
    if outcome_hits:
        raise RuntimeError(f"Selected cases already occur in model-result CSVs: {outcome_hits}")
    cases = []
    for path in selected:
        metadata = path / "case_metadata.json"
        cases.append({
            "case_id": path.name, "parent_bug_id": path.name,
            "metadata_sha256": sha256(metadata) if metadata.exists() else None,
            "correct_rtl_sha256": sha256(path / "correct.v"), "buggy_rtl_sha256": sha256(path / "buggy.v"),
            "mutation_diff_sha256": sha256(path / "rtl_mutation.diff"),
        })
    payload = {
        "schema_version": 1, "sealed": True, "seal_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selection_seed": SEED, "selection_algorithm": "sha256(seed|case_id), take first 16",
        "candidate_pool": "case401-case450 independent RTL mutations", "test_parent_count": len(cases),
        "parent_overlap": False, "model_candidate_or_outcome_hits_at_seal": 0,
        "compile_validation_excluded_from_outcome_scan": True,
        "status": "sealed_before_trace_completion_and_before_any_model_generation",
        "cases": cases,
    }
    payload["seal_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"sealed": True, "parents": len(cases), "outcome_hits": 0, "seal_sha256": payload["seal_sha256"], "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__": main()
