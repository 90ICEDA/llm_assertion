from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "rtl_cases_real_scale120"
OUT = ROOT / "rtl_cases_overfit_bait20"
GROUPS = {
    "case103_prim_onehot_addr_mismatch_suppressed": ("addr_i[1:0]", 8),
    "case126_prim_regwe_enable_gap": ("oh_i[3:0]", 5),
    "case137_prim_onehot_addr_false_positive": ("addr_i[1:0]", 7),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def divergence_bait(case_id: str, signal: str) -> tuple[int, str]:
    with (SOURCE / case_id / "waveform_good.csv").open(encoding="utf-8-sig", newline="") as h:
        good = list(csv.DictReader(h))
    with (SOURCE / case_id / "waveform_bad.csv").open(encoding="utf-8-sig", newline="") as h:
        bad = list(csv.DictReader(h))
    index = next(i for i, (g, b) in enumerate(zip(good, bad)) if g != b)
    return index, bad[index][signal]


def group_cases() -> dict[str, list[str]]:
    records = json.loads((ROOT / "outputs/formal_four_trace_representations/trace_representations.json").read_text(encoding="utf-8"))
    groups: dict[str, list[str]] = defaultdict(list)
    for item in records:
        groups[item["parent_bug_id"]].append(item["case_id"])
    return groups


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    groups = group_cases()
    manifest = []
    case_number = 1
    for parent, (bait_signal, take_count) in GROUPS.items():
        sources = groups[parent]
        by_value: dict[str, list[str]] = defaultdict(list)
        source_info = {}
        for case_id in sources:
            div_index, value = divergence_bait(case_id, bait_signal)
            by_value[value].append(case_id)
            source_info[case_id] = {"first_divergence_row": div_index, "bait_value": value}
        if len(by_value) < 4:
            raise RuntimeError(f"{parent} has only {len(by_value)} distinct bait values")
        correct_hashes = {digest(SOURCE / c / "correct.v") for c in sources}
        buggy_hashes = {digest(SOURCE / c / "buggy.v") for c in sources}
        if len(correct_hashes) != 1 or len(buggy_hashes) != 1:
            raise RuntimeError(f"RTL changes across trace variants for {parent}")
        ordered_sources = sources[:take_count]
        values = sorted(by_value)
        for primary in ordered_sources:
            primary_value = source_info[primary]["bait_value"]
            other_values = [value for value in values if value != primary_value][:3]
            heldouts = [by_value[value][0] for value in other_values]
            case_id = f"overfit{case_number:02d}_{parent.removeprefix('case').replace('_prim_', '_')}"
            target = OUT / case_id
            target.mkdir(parents=True, exist_ok=True)
            for name in ("correct.v", "buggy.v", "tb.v", "waveform_good.csv", "waveform_bad.csv"):
                shutil.copy2(SOURCE / primary / name, target / name)
            for index, heldout in enumerate(heldouts, start=1):
                primary_tb = (SOURCE / primary / "tb.v").read_text(encoding="utf-8")
                heldout_tb = (SOURCE / heldout / "tb.v").read_text(encoding="utf-8")
                primary_module = re.search(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_]*)", primary_tb).group(1)
                heldout_module = re.search(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_]*)", heldout_tb).group(1)
                # The procedural checker qualifies signals through the primary
                # testbench module.  Normalize sibling trace-harness module names
                # without changing stimulus or DUT behavior.
                heldout_tb = re.sub(rf"\b{re.escape(heldout_module)}\b", primary_module, heldout_tb)
                (target / f"tb_holdout_{index}.v").write_text(heldout_tb, encoding="utf-8")
                shutil.copy2(SOURCE / heldout / "waveform_good.csv", target / f"waveform_good_holdout_{index}.csv")
                shutil.copy2(SOURCE / heldout / "waveform_bad.csv", target / f"waveform_bad_holdout_{index}.csv")
            metadata = {
                "case_id": case_id,
                "parent_bug_id": parent,
                "primary_source_case": primary,
                "heldout_source_cases": heldouts,
                "bait_kind": "legal fixed address" if "addr" in bait_signal else "legal fixed onehot/state value",
                "bait_signal": bait_signal,
                "primary_bait_value": primary_value,
                "heldout_bait_values": other_values,
                "heldout_count": 3,
                "first_divergence_rows": {
                    "primary": source_info[primary]["first_divergence_row"],
                    **{f"heldout_{i}": source_info[h]["first_divergence_row"] for i, h in enumerate(heldouts, 1)},
                },
                "correct_rtl_sha256": next(iter(correct_hashes)),
                "buggy_rtl_sha256": next(iter(buggy_hashes)),
                "bug_value_independence_evidence": "The exact same correct and buggy RTL binaries are exercised at four distinct legal bait values, and every trace pair diverges.",
                "candidate_generalization_rule": "A candidate generalizes only if it passes correct and detects buggy behavior on primary and all three held-outs; regex hardcoding labels are auxiliary only.",
            }
            sealed_names = ["correct.v", "buggy.v", "tb.v", "waveform_good.csv", "waveform_bad.csv"]
            for i in range(1, 4):
                sealed_names += [f"tb_holdout_{i}.v", f"waveform_good_holdout_{i}.csv", f"waveform_bad_holdout_{i}.csv"]
            metadata["artifact_sha256"] = {name: digest(target / name) for name in sealed_names}
            (target / "overfit_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            manifest.append(metadata)
            case_number += 1
    if len(manifest) != 20:
        raise RuntimeError(f"Expected 20 cases, got {len(manifest)}")
    payload = {
        "schema_version": 1,
        "case_count": 20,
        "independent_parent_bug_count": len({x["parent_bug_id"] for x in manifest}),
        "not_an_independent_bug_count_claim": True,
        "minimum_heldouts_per_case": 3,
        "cases": manifest,
    }
    (OUT / "overfit20_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    selected = pd.read_csv(ROOT / "outputs/dev_locked_score_reranker/selected_candidates.csv", encoding="utf-8-sig")
    candidate_rows = []
    for item in manifest:
        source_rows = selected.loc[selected["case_id"] == item["primary_source_case"]]
        if set(source_rows["model_label"]) != {"GPT", "Claude"}:
            raise RuntimeError(f"Missing frozen dual-model candidate for {item['primary_source_case']}")
        for row in source_rows.itertuples(index=False):
            candidate_rows.append({"model": row.model_label, "model_name": row.model_name, "case_id": item["case_id"], "source_case_id": item["primary_source_case"], "candidate_index": int(row.candidate_index), "representation": row.representation, "assertion_text": row.assertion_text})
    candidate_path = ROOT / "outputs/overfit_bait20_selected_candidates.csv"
    pd.DataFrame(candidate_rows).to_csv(candidate_path, index=False, encoding="utf-8-sig")
    print(OUT / "overfit20_manifest.json")
    print(candidate_path)


if __name__ == "__main__":
    main()
