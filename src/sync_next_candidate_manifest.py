#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


REQUIRED_FILES = (
    "correct.v", "buggy.v", "mutation.diff", "spec.md", "golden.sva",
    "tb.v", "tb_holdout.v", "tb_decoy.v", "case_metadata.json",
    "weak_assertions.sva", "weak_assertions.json",
)
REQUIRED_METADATA = (
    "name", "parent_bug_id", "source_project", "source_module",
    "source_commit", "bug_class", "bug_family", "relevant_signals",
    "temporal_type", "first_divergence",
)
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("rtl_cases_real_scale210_independent_next"))
    args = parser.parse_args()
    root = args.root.resolve()
    cases, audit, failures = [], [], []

    case_dir_pattern = re.compile(r"^case\d+_")
    for case_dir in sorted(
        p for p in root.iterdir() if p.is_dir() and case_dir_pattern.match(p.name)
    ):
        errors = [f"missing {name}" for name in REQUIRED_FILES if not (case_dir / name).is_file()]
        metadata = {}
        metadata_path = case_dir / "case_metadata.json"
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"invalid metadata: {exc}")
        for key in REQUIRED_METADATA:
            if not metadata.get(key):
                errors.append(f"missing metadata {key}")
        if metadata.get("name") and metadata["name"] != case_dir.name:
            errors.append("metadata name does not match directory")
        if metadata.get("parent_bug_id") != case_dir.name:
            errors.append("parent_bug_id must uniquely identify this independent RTL mutation")
        if metadata.get("source_commit") and not HEX_COMMIT.fullmatch(str(metadata["source_commit"])):
            errors.append("source_commit is not a 40-hex commit")
        first = metadata.get("first_divergence", {})
        if not isinstance(first, dict) or set(first) != {"primary", "heldout", "decoy"}:
            errors.append("first_divergence must contain primary/heldout/decoy")
        if (case_dir / "correct.v").is_file() and (case_dir / "buggy.v").is_file():
            if (case_dir / "correct.v").read_bytes() == (case_dir / "buggy.v").read_bytes():
                errors.append("correct.v and buggy.v are identical")
        if (case_dir / "mutation.diff").is_file() and not (case_dir / "mutation.diff").read_text(encoding="utf-8").strip():
            errors.append("mutation.diff is empty")

        row = {"case_name": case_dir.name, "contract_ok": not errors, "errors": errors}
        audit.append(row)
        if errors:
            failures.append(row)
            continue
        cases.append({
            key: metadata[key] for key in (
                "name", "parent_bug_id", "source_project", "source_module",
                "source_commit", "bug_class", "bug_family", "temporal_type",
            )
        })

    manifest = {
        "schema_version": 1,
        "dataset_status": "candidate_pending_wsl_trace_and_hardness_validation",
        "admission_policy": "No case is admitted until all three correct/buggy trace variants diverge, the golden catches primary and heldout, and at least two nonvacuous weak assertions miss both buggy tracks.",
        "case_count": len(cases),
        "cases": cases,
    }
    (root / "independent_new_bug_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {
        "directory_count": len(audit),
        "contract_pass_count": len(cases),
        "contract_fail_count": len(failures),
        "all_contracts_ok": not failures,
        "manifest_sha256": digest(root / "independent_new_bug_manifest.json"),
        "failures": failures,
    }
    (root / "candidate_contract_audit.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
