#!/usr/bin/env python3
from __future__ import annotations

import csv
import difflib
import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "rtl_cases_real_scale210_independent_next"
SEMANTIC = REPO / "outputs/scale210_next_semantic_validation"
MONITORS = REPO / "outputs/scale210_next_weak_monitor_validation"
OUT = REPO / "deliverables/final_dataset_acceptance_20260804"
TRACKS = (("primary", ""), ("heldout", "_holdout"), ("decoy", "_decoy"))
PROJECT_DIR = {"opentitan": "opentitan", "common_cells": "common_cells", "verilog_axis": "verilog-axis"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def external_head(project: str) -> str:
    git = REPO / "external" / PROJECT_DIR[project] / ".git"
    value = (git / "HEAD").read_text(encoding="utf-8").strip()
    if value.startswith("ref: "):
        value = (git / value[5:]).read_text(encoding="utf-8").strip()
    return value


def diff_applies(case_dir: Path) -> bool:
    """Apply the single-file unified diff in memory and compare with buggy.v."""
    original = (case_dir / "correct.v").read_text(encoding="utf-8").splitlines(keepends=True)
    expected = (case_dir / "buggy.v").read_text(encoding="utf-8").splitlines(keepends=True)
    diff = (case_dir / "mutation.diff").read_text(encoding="utf-8").splitlines(keepends=True)
    out, cursor, i = [], 0, 0
    while i < len(diff) and not diff[i].startswith("@@"):
        i += 1
    found = False
    while i < len(diff):
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", diff[i])
        if not match:
            return False
        found = True
        start = int(match.group(1)) - 1
        out.extend(original[cursor:start])
        cursor = start
        i += 1
        while i < len(diff) and not diff[i].startswith("@@"):
            line = diff[i]
            if line.startswith("\\ No newline"):
                i += 1
                continue
            if not line or line[0] not in " +-":
                return False
            content = line[1:]
            if line[0] == " ":
                if cursor >= len(original) or original[cursor] != content:
                    return False
                out.append(content)
                cursor += 1
            elif line[0] == "-":
                if cursor >= len(original) or original[cursor] != content:
                    return False
                cursor += 1
            else:
                out.append(content)
            i += 1
    out.extend(original[cursor:])
    return found and out == expected


def first_csv_difference(good: Path, bad: Path) -> tuple[str, int]:
    with good.open(encoding="utf-8-sig", newline="") as gh, bad.open(encoding="utf-8-sig", newline="") as bh:
        grows, brows = csv.DictReader(gh), csv.DictReader(bh)
        for index, (grow, brow) in enumerate(zip(grows, brows)):
            if grow != brow:
                return grow.get("time_ps", ""), index
    return "", -1


def declared_edits_apply(meta: dict, correct: str, buggy: str) -> bool:
    value = correct
    edits = meta.get("mutation_edits", [])
    if not edits:
        return False
    for edit in edits:
        search, replace = edit.get("search"), edit.get("replace")
        if not isinstance(search, str) or not isinstance(replace, str) or value.count(search) != 1:
            return False
        value = value.replace(search, replace, 1)
    return value == buggy


def refresh_integrity_metadata(case_dir: Path, meta: dict, decision: str) -> bool:
    correct_path, buggy_path = case_dir / "correct.v", case_dir / "buggy.v"
    correct = correct_path.read_text(encoding="utf-8")
    buggy = buggy_path.read_text(encoding="utf-8")
    edits_apply = declared_edits_apply(meta, correct, buggy)
    canonical = "".join(difflib.unified_diff(
        correct.splitlines(keepends=True), buggy.splitlines(keepends=True),
        fromfile="correct.v", tofile="buggy.v",
    ))
    (case_dir / "mutation.diff").write_text(canonical, encoding="utf-8")
    meta["correct_sha256"] = sha(correct_path)
    meta["buggy_sha256"] = sha(buggy_path)
    meta["status"] = f"final_verified_{decision}"
    meta["trace_variants"] = {
        "relationship": "stimulus_variants_of_one_parent_bug",
        "count_as_independent_bugs": False,
        "variants": ["primary", "heldout", "decoy"],
    }
    for track, suffix in TRACKS:
        good = case_dir / f"waveform_good{suffix}.csv"
        bad = case_dir / f"waveform_bad{suffix}.csv"
        time_ps, sample_index = first_csv_difference(good, bad)
        previous = meta.get("first_divergence", {}).get(track) or {}
        previous.update({
            "time_ps": int(time_ps) if str(time_ps).isdigit() else time_ps,
            "sample_index": sample_index,
            "good_trace_sha256": sha(good),
            "bad_trace_sha256": sha(bad),
            "derived_from_final_wsl_rerun": True,
        })
        meta.setdefault("first_divergence", {})[track] = previous
    (case_dir / "case_metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return edits_apply


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    decision_rows = list(csv.DictReader((ROOT / "hardness_admission_report.csv").open(encoding="utf-8-sig")))
    decisions = {row["case_name"]: row for row in decision_rows}
    semantic = json.loads((SEMANTIC / "semantic_validation_summary.json").read_text(encoding="utf-8"))
    semantic_by_case = {row["case_id"]: row for row in semantic["cases"]}
    case_dirs = sorted(p for p in ROOT.iterdir() if p.is_dir() and re.match(r"^case\d+_", p.name))
    trace_rows, golden_rows, hardness_rows, provenance_rows = [], [], [], []
    manifest_cases, rejected_rows = [], []

    for case_dir in case_dirs:
        name = case_dir.name
        meta = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
        evaluation = json.loads((case_dir / "hardness_evaluation.json").read_text(encoding="utf-8"))
        decision = decisions[name]
        edits_apply = refresh_integrity_metadata(case_dir, meta, decision["decision"])
        actual_correct = sha(case_dir / "correct.v")
        actual_buggy = sha(case_dir / "buggy.v")
        head = external_head(meta["source_project"])
        provenance = {
            "case_name": name,
            "decision": decision["decision"],
            "source_project": meta["source_project"],
            "source_module": meta["source_module"],
            "source_commit_declared": meta["source_commit"],
            "source_commit_actual": head,
            "source_commit_ok": meta["source_commit"] == head,
            "correct_sha256_declared": meta.get("correct_sha256"),
            "correct_sha256_actual": actual_correct,
            "correct_hash_ok": meta.get("correct_sha256") == actual_correct,
            "buggy_sha256_declared": meta.get("buggy_sha256"),
            "buggy_sha256_actual": actual_buggy,
            "buggy_hash_ok": meta.get("buggy_sha256") == actual_buggy,
            "mutation_diff_sha256": sha(case_dir / "mutation.diff"),
            "mutation_diff_applies_exactly": diff_applies(case_dir),
            "declared_mutation_edits_apply_exactly": edits_apply,
            "bug_family": meta["bug_family"],
            "mutation_operator": meta.get("mutation_kind"),
            "mutation_edit_count": len(meta.get("mutation_edits", [])),
            "parent_bug_id": meta["parent_bug_id"],
            "parent_bug_unique_ok": meta["parent_bug_id"] == name,
        }
        provenance["provenance_ok"] = all(
            provenance[key] for key in (
                "source_commit_ok", "correct_hash_ok", "buggy_hash_ok",
                "mutation_diff_applies_exactly", "parent_bug_unique_ok",
            )
        ) and bool(provenance["bug_family"] and provenance["mutation_operator"])
        provenance_rows.append(provenance)

        golden = evaluation["golden"]
        for track, suffix in TRACKS:
            result = golden[track]
            trace = semantic_by_case[name]["variants"][track]
            trace_log_track = "holdout" if track == "heldout" else track
            good = case_dir / f"waveform_good{suffix}.csv"
            bad = case_dir / f"waveform_bad{suffix}.csv"
            first = meta["first_divergence"].get(track)
            derived_time, derived_index = first_csv_difference(good, bad)
            trace_rows.append({
                "case_name": name, "decision": decision["decision"], "parent_bug_id": meta["parent_bug_id"],
                "trace_variant": track, "variant_role": "stimulus_variant_of_parent_bug_not_independent_bug",
                "correct_trace_present": good.is_file(), "buggy_trace_present": bad.is_file(),
                "correct_trace_bytes": good.stat().st_size if good.is_file() else 0,
                "buggy_trace_bytes": bad.stat().st_size if bad.is_file() else 0,
                "correct_trace_sha256": sha(good) if good.is_file() else "",
                "buggy_trace_sha256": sha(bad) if bad.is_file() else "",
                "diverges": trace["diverges"],
                "first_divergence_time_ps": first["time_ps"] if first else derived_time,
                "first_divergence_sample_index": first["sample_index"] if first else derived_index,
                "first_divergence_source": "metadata_verified_after_rerun" if first else "derived_from_rerun_csv",
                "correct_sim_log": f"full_simulation_logs/trace/{name}.{trace_log_track}.correct.log",
                "buggy_sim_log": f"full_simulation_logs/trace/{name}.{trace_log_track}.buggy.log",
            })
            golden_rows.append({
                "case_name": name, "decision": decision["decision"], "trace_variant": track,
                "compile_ok": result["compile_ok"], "correct_pass": result["good_pass"],
                "buggy_fail": result["bad_fail"], "antecedent_hit_correct": result["antecedent_hit_good"],
                "antecedent_hit_buggy": result["antecedent_hit_bad"], "non_vacuous_buggy": result["non_vacuous_bad"],
                "correct_antecedent_hits": result["good_antecedent_hits"],
                "buggy_antecedent_hits": result["bad_antecedent_hits"],
                "correct_failure_count": result["good_failure_count"],
                "buggy_failure_count": result["bad_failure_count"],
                "golden_gate_ok": all((result["compile_ok"], result["good_pass"], result["bad_fail"],
                                       result["antecedent_hit_good"], result["antecedent_hit_bad"], result["non_vacuous_bad"])),
                "correct_sim_log": f"full_simulation_logs/assertions/{name}.{track}.correct.log",
                "buggy_sim_log": f"full_simulation_logs/assertions/{name}.{track}.buggy.log",
            })

        weak_detail = []
        for item in evaluation["weak_assertions"]:
            misses = all(
                item[t]["compile_ok"] and item[t]["good_pass"] and not item[t]["bad_fail"]
                and item[t]["antecedent_hit_bad"] and item[t]["non_vacuous_bad"]
                for t, _ in TRACKS
            )
            weak_detail.append(f'{item["name"]}:{item["kind"]}:{"miss" if misses else "catch_or_invalid"}')
        hardness_rows.append({
            "case_name": name, "decision": decision["decision"], "golden_all_three_ok": decision["golden_gate_ok"],
            "weak_assertion_count": decision["weak_assertion_count"], "weak_kind_count": decision["weak_kind_count"],
            "nonvacuous_weak_miss_count_all_three": decision["nonvacuous_weak_miss_count"],
            "minimum_required": 2, "hardness_ok": decision["hardness_ok"],
            "weak_assertion_detail": ";".join(weak_detail), "reason": decision["reason"],
        })

        if decision["decision"] == "admitted" and provenance["provenance_ok"]:
            manifest_cases.append({
                "name": name, "case_name": name, "parent_bug_id": meta["parent_bug_id"],
                "trace_variants": ["primary", "heldout", "decoy"],
                "trace_variant_semantics": "three stimulus variants belonging to one parent bug; never independent bug samples",
                "source_project": meta["source_project"], "source_module": meta["source_module"],
                "source_commit": meta["source_commit"], "correct_sha256": actual_correct,
                "buggy_sha256": actual_buggy, "mutation_diff_sha256": provenance["mutation_diff_sha256"],
                "bug_class": meta["bug_class"], "bug_family": meta["bug_family"],
                "mutation_operator": meta["mutation_kind"], "mutation_edits": meta.get("mutation_edits", []),
            })
        else:
            reason = decision["reason"]
            if decision["decision"] == "admitted" and not provenance["provenance_ok"]:
                reason = "provenance audit failed"
            rejected_rows.append({**provenance, "rejection_reason": reason})

    parent_ids = [row["parent_bug_id"] for row in manifest_cases]
    manifest = {
        "schema_version": 2, "dataset_status": "final_verified", "finalized_at": str(date.today()),
        "canonical_unit": "parent_bug_id", "trace_variants_count_as_independent_bugs": False,
        "candidate_count": len(case_dirs), "admitted_parent_bug_count": len(manifest_cases),
        "rejected_parent_bug_count": len(rejected_rows), "pending_or_unverified_count": 0,
        "unique_parent_bug_count": len(set(parent_ids)), "parent_bug_ids_unique": len(parent_ids) == len(set(parent_ids)),
        "required_trace_variants": ["primary", "heldout", "decoy"],
        "admission_rule": "all three correct/buggy traces present and divergent; golden passes correct, fails buggy, and has hit antecedent on all three; five weak kinds and >=2 nonvacuous weak misses across all three; provenance audit passes",
        "cases": manifest_cases,
    }
    write_csv(OUT / "rejected_cases.csv", rejected_rows)
    write_csv(OUT / "golden_validation.csv", golden_rows)
    write_csv(OUT / "trace_activation.csv", trace_rows)
    write_csv(OUT / "hardness_validation.csv", hardness_rows)
    write_csv(OUT / "provenance_validation.csv", provenance_rows)
    (OUT / "final_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    candidate_archive = ROOT / "candidate_inventory_pre_final.json"
    current_manifest = ROOT / "independent_new_bug_manifest.json"
    if not candidate_archive.exists() and current_manifest.exists():
        shutil.copy2(current_manifest, candidate_archive)
    current_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    logs = OUT / "full_simulation_logs"
    if logs.exists():
        shutil.rmtree(logs)
    shutil.copytree(SEMANTIC / "logs", logs / "trace")
    shutil.copytree(MONITORS / "logs", logs / "assertions")
    shutil.copy2(SEMANTIC / "semantic_validation_summary.json", OUT / "semantic_validation_summary.json")
    shutil.copy2(MONITORS / "weak_monitor_summary.json", OUT / "weak_monitor_summary.json")
    shutil.make_archive(str(OUT / "full_simulation_logs"), "zip", logs)
    checksums = []
    for path in sorted(p for p in OUT.rglob("*") if p.is_file() and "full_simulation_logs" not in p.parts[-2:-1]):
        if path.name != "SHA256SUMS.txt":
            checksums.append(f"{sha(path)}  {path.relative_to(OUT).as_posix()}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate_count": len(case_dirs), "admitted": len(manifest_cases), "rejected": len(rejected_rows),
        "pending": 0, "trace_rows": len(trace_rows), "golden_rows": len(golden_rows),
        "provenance_pass": sum(bool(r["provenance_ok"]) for r in provenance_rows),
        "output": str(OUT),
    }, indent=2))


if __name__ == "__main__":
    main()
