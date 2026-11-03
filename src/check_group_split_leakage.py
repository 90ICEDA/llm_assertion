from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

SCHEMES = {
    "parent_held_out": "parent_bug_id",
    "module_held_out": "source_module",
    "bug_family_held_out": "bug_family",
    "source_project_held_out": "source_project",
}
SPLITS = {"train", "dev", "test"}


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--split-dir", required=True); args = ap.parse_args()
    root = Path(args.split_dir).resolve(); manifest_path = root / "split_manifest.json"; manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    universe = pd.read_csv(root / "split_universe.csv", encoding="utf-8-sig"); failures = []; scheme_report = {}
    if universe.case_id.duplicated().any(): failures.append("universe contains duplicate case_id")
    for scheme, heldout_column in SCHEMES.items():
        path = root / f"{scheme}.csv"; variants_path = root / f"{scheme}_trace_variants.csv"
        frame = pd.read_csv(path, encoding="utf-8-sig"); variants = pd.read_csv(variants_path, encoding="utf-8-sig")
        local = []
        if set(frame.split) != SPLITS: local.append(f"split labels are {sorted(set(frame.split))}, expected {sorted(SPLITS)}")
        if set(frame.case_id) != set(universe.case_id) or len(frame) != len(universe): local.append("case coverage differs from universe")
        for column in ("case_id", "parent_bug_id"):
            leaked = frame.groupby(column).split.nunique(); leaked = leaked[leaked > 1]
            if len(leaked): local.append(f"{column} overlap across splits: {leaked.index.tolist()[:10]}")
        leaked_group = frame.groupby(heldout_column).split.nunique(); leaked_group = leaked_group[leaked_group > 1]
        if len(leaked_group): local.append(f"{heldout_column} overlap across splits: {leaked_group.index.tolist()[:10]}")
        expected_variants = {(case, variant) for case in universe.case_id for variant in ("primary", "heldout", "decoy")}
        actual_variants = set(zip(variants.case_id, variants.trace_variant))
        if actual_variants != expected_variants or len(variants) != 3 * len(universe): local.append("trace variant coverage is incomplete or duplicated")
        parent_variant_leak = variants.groupby("parent_bug_id").split.nunique(); parent_variant_leak = parent_variant_leak[parent_variant_leak > 1]
        if len(parent_variant_leak): local.append("trace variants of a parent cross splits")
        for output, expected in manifest["output_sha256"].items():
            p = Path(output)
            if p.name in {path.name, variants_path.name} and (not p.exists() or sha(p) != expected): local.append(f"frozen hash mismatch: {p.name}")
        scheme_report[scheme] = {"pass": not local, "failures": local}
        failures.extend(f"{scheme}: {item}" for item in local)
    report = {"schema_version": 1, "all_pass": not failures, "failure_count": len(failures), "failures": failures, "schemes": scheme_report}
    report_path = root / "leakage_audit.json"; report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["status"] = "frozen_leakage_audit_passed" if not failures else "leakage_audit_failed"
    manifest["leakage_audit_sha256"] = sha(report_path); manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if failures: sys.exit(1)


if __name__ == "__main__": main()
