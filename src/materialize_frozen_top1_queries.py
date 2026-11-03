from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "outputs/behavioral_preference_pilot_v1"
SPLITS = ROOT / "outputs/formal_group_heldout_splits_v1"
OUT = PILOT / "frozen_top1_v1"
TRAIN = PILOT / "selected_train_parents.csv"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def spec_path(case: Path) -> Path:
    options = (case / "spec.md", case / "experiment/spec.txt", case / "spec.txt")
    found = next((p for p in options if p.is_file()), None)
    if found is None:
        raise RuntimeError(f"no specification in {case}")
    return found


def visible(tb: str) -> list[str]:
    clean = re.sub(r"//.*?$|/\*.*?\*/", "", tb, flags=re.M | re.S)
    out = []
    for match in re.finditer(r"\b(?:reg|wire|logic)\b([^;]*);", clean):
        declaration = re.sub(r"\[[^\]]+\]", " ", match.group(1))
        declaration = re.sub(r"\b(?:signed|unsigned)\b", " ", declaration)
        for item in declaration.split(","):
            name = re.search(r"([A-Za-z_]\w*)\s*$", item.split("=", 1)[0].strip())
            if name:
                out.append(name.group(1))
    return list(dict.fromkeys(out))


def main() -> None:
    train = read_csv(TRAIN)
    train_parents = {r["parent_bug_id"] for r in train}
    train_families = {r["bug_family"] for r in train}
    train_projects = {r["source_project"] for r in train}
    parent_test = [r for r in read_csv(SPLITS / "parent_held_out.csv")
                   if r["split"] == "test" and r["parent_bug_id"] not in train_parents]
    family_test = [r for r in read_csv(SPLITS / "bug_family_held_out.csv")
                   if r["split"] == "test" and r["parent_bug_id"] not in train_parents
                   and r["bug_family"] not in train_families]
    assert len(parent_test) == 35 and len({r["parent_bug_id"] for r in parent_test}) == 18
    assert len(family_test) == 25 and len({r["bug_family"] for r in family_test}) == 8
    by_case: dict[str, dict] = {}
    for split_name, rows in (("unseen_parent", parent_test), ("unseen_bug_family", family_test)):
        for row in rows:
            rec = by_case.setdefault(row["case_id"], {**row, "memberships": []})
            rec["memberships"].append(split_name)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    forbidden_prompt_terms = ("heldout", "held-out", "fp set", "tp set", "test outcome", "target_detect")
    for case_id in sorted(by_case):
        row = by_case[case_id]
        case = ROOT / row["dataset_root"] / case_id
        spec, rtl, tb = spec_path(case), case / "correct.v", case / "tb.v"
        if not rtl.is_file() or not tb.is_file():
            raise FileNotFoundError(case)
        signals = visible(tb.read_text(encoding="utf-8"))
        prompt = f"""Generate exactly one SystemVerilog concurrent assertion (SVA) and no prose.
Use only signals visible at the testbench/DUT top level. The assertion must compile, be safe on the correct RTL, detect the specified defect, and be non-vacuous.
Case: {case_id}
Project: {row['source_project']}
Module: {row['source_module']}
Bug family: {row['bug_family']}
Specification:
{spec.read_text(encoding='utf-8')}

Correct RTL:
{rtl.read_text(encoding='utf-8')}

Visible top-level signals:
{', '.join(signals)}
"""
        lowered = prompt.lower()
        hits = [term for term in forbidden_prompt_terms if term in lowered]
        if hits:
            raise RuntimeError(f"forbidden outcome-like text in {case_id}: {hits}")
        qdir = OUT / "queries" / case_id
        qdir.mkdir(parents=True, exist_ok=True)
        prompt_path = qdir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        records.append({
            "query_id": hashlib.sha256(("frozen_top1_v1\0" + case_id).encode()).hexdigest()[:24],
            "case_id": case_id, "parent_bug_id": row["parent_bug_id"],
            "source_project": row["source_project"], "source_module": row["source_module"],
            "bug_family": row["bug_family"], "bug_class": row["bug_class"],
            "dataset_root": row["dataset_root"], "memberships": sorted(row["memberships"]),
            "prompt_path": str(prompt_path.relative_to(ROOT)).replace("\\", "/"),
            "prompt_sha256": sha(prompt_path), "spec_sha256": sha(spec),
            "spec_path": str(spec.relative_to(ROOT)).replace("\\", "/"),
            "correct_rtl_sha256": sha(rtl), "tb_sha256": sha(tb),
            "visible_signal_count": len(signals),
        })
    manifest = {
        "status": "frozen_before_any_top1_generation", "version": "frozen_top1_v1",
        "train_parent_count": len(train_parents), "train_projects": sorted(train_projects),
        "query_count": len(records),
        "split_counts": {"unseen_parent": len(parent_test), "unseen_bug_family": len(family_test)},
        "strict_group_counts": {"unseen_parent_parents": 18, "unseen_bug_family_parents": 9,
                                "unseen_bug_families": 8},
        "project_ood": {"status": "not_constructible", "reason": "Pilot training covers all three frozen projects"},
        "decode": {"temperature": 0.0, "do_sample": False, "num_return_sequences": 1,
                   "max_new_tokens": 512, "reranker": False, "repair": False,
                   "selector": False, "heldout_information": False},
        "records": records,
    }
    manifest_path = OUT / "query_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    audit = {
        "status": "pass", "query_manifest_sha256": sha(manifest_path),
        "pilot_parent_overlap_unseen_parent": 0, "pilot_family_overlap_unseen_bug_family": 0,
        "prompt_forbidden_term_hits": 0, "buggy_rtl_in_model_input": False,
        "fp_tp_in_model_input": False, "outcome_fields_in_model_input": False,
        "all_prompt_hashes_unique": len({r["prompt_sha256"] for r in records}) == len(records),
    }
    (OUT / "pre_generation_leakage_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"query_count": len(records), "split_counts": manifest["split_counts"],
                      "overlap_queries": sum(len(r["memberships"]) == 2 for r in records), "audit": audit}, sort_keys=True))


if __name__ == "__main__":
    main()
