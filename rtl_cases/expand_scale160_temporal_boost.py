#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = ROOT / "rtl_cases_real_scale120"
DEFAULT_OUTPUT_ROOT = ROOT / "rtl_cases_real_scale160_temporal_boosted"
DEFAULT_FORMAL_GOLDEN = ROOT / "outputs" / "golden_recheck_scale120_formal.csv"
DEFAULT_HARDNESS = ROOT / "outputs" / "hardness_scale120_wsl.csv"
DEFAULT_DIVERGENCE = ROOT / "outputs" / "trace_divergence_scale120_wsl.csv"

TEMPORAL_SEED_NAMES = [
    "case110_prim_intr_event_overwrite",
    "case112_prim_intr_test_pulse_dropped",
    "case113_prim_edge_posedge_misdecoded",
    "case114_prim_edge_negedge_misdecoded",
    "case115_prim_edge_both_edges_collapsed",
    "case116_prim_filter_late_accept",
    "case117_prim_filter_bypass_stale",
    "case118_prim_filter_ctr_early_accept",
    "case119_prim_filter_ctr_late_accept",
    "case120_prim_filter_ctr_bypass_stale",
    "case122_prim_filter_ctr_streak_reset_ignored",
    "case123_prim_edge_sync_output_lag",
    "case124_prim_fifo_clear_ignored",
    "case125_prim_fifo_wrap_late",
    "case127_prim_intr_status_test_qe_ignored",
    "case128_prim_intr_event_mask_stall",
    "case132_prim_edge_posedge_missing",
    "case133_prim_edge_negedge_missing",
    "case134_prim_intr_event_not_sticky",
]


@dataclass(frozen=True)
class TrackPlan:
    plan_name: str
    primary_source: str
    holdout_source: str
    decoy_source: str
    name_tag: str


BASE_PLANS: list[TrackPlan] = [
    TrackPlan(
        plan_name="seen_from_holdout",
        primary_source="holdout",
        holdout_source="primary",
        decoy_source="decoy",
        name_tag="seen_holdout",
    ),
    TrackPlan(
        plan_name="seen_from_decoy",
        primary_source="decoy",
        holdout_source="holdout",
        decoy_source="primary",
        name_tag="seen_decoy",
    ),
]

PLAN_OVERRIDES: dict[str, list[TrackPlan]] = {
    "case118_prim_filter_ctr_early_accept": [
        TrackPlan(
            plan_name="seen_from_holdout_decoy_from_holdout",
            primary_source="holdout",
            holdout_source="primary",
            decoy_source="holdout",
            name_tag="seen_holdout",
        ),
        TrackPlan(
            plan_name="seen_from_primary_decoy_from_holdout",
            primary_source="primary",
            holdout_source="holdout",
            decoy_source="holdout",
            name_tag="seen_primary",
        ),
    ],
    "case119_prim_filter_ctr_late_accept": [
        TrackPlan(
            plan_name="seen_from_holdout_decoy_from_holdout",
            primary_source="holdout",
            holdout_source="primary",
            decoy_source="holdout",
            name_tag="seen_holdout",
        ),
        TrackPlan(
            plan_name="seen_from_primary_decoy_from_holdout",
            primary_source="primary",
            holdout_source="holdout",
            decoy_source="holdout",
            name_tag="seen_primary",
        ),
    ],
}

EXTRA_PLANS: dict[str, list[TrackPlan]] = {
    "case110_prim_intr_event_overwrite": [
        TrackPlan(
            plan_name="rotate_all_tracks",
            primary_source="holdout",
            holdout_source="decoy",
            decoy_source="primary",
            name_tag="rotate_tracks",
        )
    ],
    "case124_prim_fifo_clear_ignored": [
        TrackPlan(
            plan_name="rotate_all_tracks",
            primary_source="holdout",
            holdout_source="decoy",
            decoy_source="primary",
            name_tag="rotate_tracks",
        )
    ],
}

TRACK_FILES = {
    "primary": {
        "tb": "tb.v",
        "good_csv": "waveform_good.csv",
        "bad_csv": "waveform_bad.csv",
        "good_vcd": "waveform_good.vcd",
        "bad_vcd": "waveform_bad.vcd",
        "trace_good": "trace_good.txt",
        "trace_bad": "trace_bad.txt",
    },
    "holdout": {
        "tb": "tb_holdout.v",
        "good_csv": "waveform_good_holdout.csv",
        "bad_csv": "waveform_bad_holdout.csv",
        "good_vcd": "waveform_good_holdout.vcd",
        "bad_vcd": "waveform_bad_holdout.vcd",
        "trace_good": "trace_good_holdout.txt",
        "trace_bad": "trace_bad_holdout.txt",
    },
    "decoy": {
        "tb": "tb_decoy.v",
        "good_csv": "waveform_good_decoy.csv",
        "bad_csv": "waveform_bad_decoy.csv",
        "good_vcd": "waveform_good_decoy.vcd",
        "bad_vcd": "waveform_bad_decoy.vcd",
        "trace_good": None,
        "trace_bad": None,
    },
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_manifest(root: Path) -> list[dict]:
    return read_json(root / "case_manifest.json")["cases"]


def write_manifest(root: Path, cases: list[dict]) -> None:
    write_json(root / "case_manifest.json", {"cases": cases})


def read_csv_lookup(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row["case_name"]): row
            for row in csv.DictReader(handle)
        }


def bool_field(row: dict[str, str], key: str) -> bool:
    return str(row.get(key, "")).strip().lower() == "true"


def tb_case_id(case_name: str) -> str:
    return case_name.split("_", 1)[0]


def rewrite_tb_text(tb_text: str, *, new_case_name: str, role: str, source_seed: str, source_track: str) -> str:
    new_id = tb_case_id(new_case_name)
    old_id = tb_case_id(source_seed)
    suffix = {
        "primary": ".vcd",
        "holdout": "_holdout.vcd",
        "decoy": "_decoy.vcd",
    }[role]

    out = tb_text
    out = re.sub(rf"\bmodule\s+tb_{re.escape(old_id)}\b", f"module tb_{new_id}", out, count=1)
    out = re.sub(rf"\btb_{re.escape(old_id)}\b", f"tb_{new_id}", out)
    out = re.sub(r'\$dumpfile\(".*?"\);', f'$dumpfile("{new_id}{suffix}");', out, count=1)
    banner = (
        f"// AF_TEMPORAL_VARIANT_SOURCE: case={source_seed}, track={source_track}, role={role}\n"
    )
    if not out.startswith("// AF_TEMPORAL_VARIANT_SOURCE:"):
        out = banner + out
    return out


def copy_track_files(
    *,
    source_dir: Path,
    target_dir: Path,
    source_track: str,
    target_role: str,
    new_case_name: str,
    source_seed: str,
) -> dict[str, str]:
    src = TRACK_FILES[source_track]
    tb_name = {
        "primary": "tb.v",
        "holdout": "tb_holdout.v",
        "decoy": "tb_decoy.v",
    }[target_role]
    good_csv_name = {
        "primary": "waveform_good.csv",
        "holdout": "waveform_good_holdout.csv",
        "decoy": "waveform_good_decoy.csv",
    }[target_role]
    bad_csv_name = {
        "primary": "waveform_bad.csv",
        "holdout": "waveform_bad_holdout.csv",
        "decoy": "waveform_bad_decoy.csv",
    }[target_role]
    good_vcd_name = {
        "primary": "waveform_good.vcd",
        "holdout": "waveform_good_holdout.vcd",
        "decoy": "waveform_good_decoy.vcd",
    }[target_role]
    bad_vcd_name = {
        "primary": "waveform_bad.vcd",
        "holdout": "waveform_bad_holdout.vcd",
        "decoy": "waveform_bad_decoy.vcd",
    }[target_role]

    tb_text = (source_dir / src["tb"]).read_text(encoding="utf-8")
    rewritten_tb = rewrite_tb_text(
        tb_text,
        new_case_name=new_case_name,
        role=target_role,
        source_seed=source_seed,
        source_track=source_track,
    )
    (target_dir / tb_name).write_text(rewritten_tb, encoding="utf-8", newline="\n")
    shutil.copy2(source_dir / src["good_csv"], target_dir / good_csv_name)
    shutil.copy2(source_dir / src["bad_csv"], target_dir / bad_csv_name)
    if (source_dir / src["good_vcd"]).exists():
        shutil.copy2(source_dir / src["good_vcd"], target_dir / good_vcd_name)
    if (source_dir / src["bad_vcd"]).exists():
        shutil.copy2(source_dir / src["bad_vcd"], target_dir / bad_vcd_name)
    return {
        "tb": tb_name,
        "good_csv": good_csv_name,
        "bad_csv": bad_csv_name,
    }


def append_variant_notes(case_dir: Path, *, seed_name: str, new_case_name: str, plan: TrackPlan) -> None:
    notes_path = case_dir / "STIMULUS_NOTES.md"
    block = "\n".join(
        [
            "",
            "## Temporal Bootstrap Variant",
            "",
            f"- Variant case: `{new_case_name}`",
            f"- Seed case: `{seed_name}`",
            f"- Track plan: `{plan.plan_name}`",
            f"- Primary trace source: `{plan.primary_source}`",
            f"- Held-out trace source: `{plan.holdout_source}`",
            f"- Decoy trace source: `{plan.decoy_source}`",
            "- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.",
            "",
        ]
    )
    if notes_path.exists():
        text = notes_path.read_text(encoding="utf-8")
        if "## Temporal Bootstrap Variant" not in text:
            notes_path.write_text(text.rstrip() + "\n" + block, encoding="utf-8", newline="\n")


def inherited_track_ok(formal_row: dict[str, str], track_name: str) -> bool:
    if track_name == "primary":
        return (
            bool_field(formal_row, "compile_ok")
            and bool_field(formal_row, "pass_on_correct")
            and bool_field(formal_row, "fail_on_buggy")
            and bool_field(formal_row, "antecedent_triggered")
        )
    if track_name == "holdout":
        return (
            bool_field(formal_row, "heldout_correct_pass")
            and bool_field(formal_row, "heldout_buggy_fail")
            and bool_field(formal_row, "heldout_antecedent_hit")
        )
    if track_name == "decoy":
        return (
            bool_field(formal_row, "decoy_correct_pass")
            and bool_field(formal_row, "decoy_buggy_fail")
            and bool_field(formal_row, "decoy_antecedent_hit")
        )
    raise ValueError(f"Unknown track: {track_name}")


def build_variant_entry(seed_entry: dict, *, new_case_name: str, plan: TrackPlan) -> dict:
    entry = json.loads(json.dumps(seed_entry))
    entry["name"] = new_case_name
    entry["seed_case_name"] = seed_entry["name"]
    # A case is a trace-role variant, not a new bug.  Keep the bug identity
    # explicit so downstream benchmark summaries cannot accidentally count
    # track permutations as independent bugs.
    entry["parent_bug_id"] = seed_entry.get("parent_bug_id", seed_entry["name"])
    entry["dataset_phase"] = "scale160_temporal_boost_variant"
    entry["status"] = "inherited_seed_track_validation"
    entry["variant_parent_case"] = seed_entry["name"]
    entry["variant_track_plan"] = plan.plan_name
    entry["variant_primary_source_track"] = plan.primary_source
    entry["variant_holdout_source_track"] = plan.holdout_source
    entry["variant_decoy_source_track"] = plan.decoy_source
    entry["overfit_decoy_source_case"] = seed_entry["name"]
    entry["overfit_decoy_strategy"] = f"track_permutation:{plan.plan_name}"
    entry["overfit_lure"] = (
        f"Bootstrap temporal variant derived from {seed_entry['name']}: the visible trace roles are permuted "
        f"(primary={plan.primary_source}, holdout={plan.holdout_source}, decoy={plan.decoy_source}) while preserving "
        "the same OpenTitan bug relation, so a literal pin to one witnessed timing prelude should fail to generalize."
    )
    return entry


def variant_plans_for_seed(seed_name: str) -> list[TrackPlan]:
    return list(PLAN_OVERRIDES.get(seed_name, BASE_PLANS)) + list(EXTRA_PLANS.get(seed_name, []))


def ensure_seed_reports_ok(
    *,
    seed_name: str,
    formal_lookup: dict[str, dict[str, str]],
    hardness_lookup: dict[str, dict[str, str]],
    divergence_lookup: dict[str, dict[str, str]],
) -> None:
    if seed_name not in formal_lookup:
        raise KeyError(f"Missing formal golden row for {seed_name}")
    if seed_name not in hardness_lookup:
        raise KeyError(f"Missing hardness row for {seed_name}")
    if seed_name not in divergence_lookup:
        raise KeyError(f"Missing divergence row for {seed_name}")

    formal = formal_lookup[seed_name]
    hardness = hardness_lookup[seed_name]
    divergence = divergence_lookup[seed_name]
    required = [
        bool_field(formal, "golden_ok"),
        bool_field(formal, "reachability_gate_ok"),
        bool_field(hardness, "hardness_ok"),
        bool_field(divergence, "divergence_gate_ok"),
    ]
    if not all(required):
        raise RuntimeError(f"Seed case failed prerequisite validation gates: {seed_name}")


def run_prepare_prompt_assets(root: Path) -> None:
    cmd = [sys.executable, str(ROOT / "rtl_cases" / "prepare_prompt_assets.py"), "--root", str(root)]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"prepare_prompt_assets failed for {root}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


def create_variants(
    *,
    source_root: Path,
    output_root: Path,
    formal_lookup: dict[str, dict[str, str]],
    hardness_lookup: dict[str, dict[str, str]],
    divergence_lookup: dict[str, dict[str, str]],
) -> tuple[list[dict], list[dict]]:
    source_manifest = load_manifest(source_root)
    seed_lookup = {str(entry["name"]): entry for entry in source_manifest}
    # Normalize bug identity for the whole benchmark, not only the newly
    # generated trace-role variants. Seed cases are independent bugs;
    # augmentation cases inherit their seed's bug identity.
    for entry in source_manifest:
        entry["parent_bug_id"] = entry.get("parent_bug_id") or entry.get("seed_case_name") or entry["name"]
    new_manifest = list(source_manifest)
    new_rows: list[dict] = []
    next_case_num = 301

    for seed_name in TEMPORAL_SEED_NAMES:
        ensure_seed_reports_ok(
            seed_name=seed_name,
            formal_lookup=formal_lookup,
            hardness_lookup=hardness_lookup,
            divergence_lookup=divergence_lookup,
        )
        seed_entry = seed_lookup[seed_name]
        seed_dir = output_root / seed_name
        for plan in variant_plans_for_seed(seed_name):
            new_case_name = f"case{next_case_num}_{plan.name_tag}_from_{seed_name}"
            next_case_num += 1
            target_dir = output_root / new_case_name
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(seed_dir, target_dir)
            if (target_dir / "experiment").exists():
                shutil.rmtree(target_dir / "experiment")

            copy_track_files(
                source_dir=seed_dir,
                target_dir=target_dir,
                source_track=plan.primary_source,
                target_role="primary",
                new_case_name=new_case_name,
                source_seed=seed_name,
            )
            copy_track_files(
                source_dir=seed_dir,
                target_dir=target_dir,
                source_track=plan.holdout_source,
                target_role="holdout",
                new_case_name=new_case_name,
                source_seed=seed_name,
            )
            copy_track_files(
                source_dir=seed_dir,
                target_dir=target_dir,
                source_track=plan.decoy_source,
                target_role="decoy",
                new_case_name=new_case_name,
                source_seed=seed_name,
            )
            append_variant_notes(target_dir, seed_name=seed_name, new_case_name=new_case_name, plan=plan)

            manifest_entry = build_variant_entry(seed_entry, new_case_name=new_case_name, plan=plan)
            new_manifest.append(manifest_entry)

            formal_row = formal_lookup[seed_name]
            new_rows.append(
                {
                    "case_name": new_case_name,
                    "seed_case_name": seed_name,
                    "parent_bug_id": seed_entry.get("parent_bug_id", seed_name),
                    "variant_track_plan": plan.plan_name,
                    "primary_source_track": plan.primary_source,
                    "holdout_source_track": plan.holdout_source,
                    "decoy_source_track": plan.decoy_source,
                    "seed_formal_golden_ok": bool_field(formal_row, "golden_ok"),
                    "seed_formal_reachability_ok": bool_field(formal_row, "reachability_gate_ok"),
                    "seed_hardness_ok": bool_field(hardness_lookup[seed_name], "hardness_ok"),
                    "seed_divergence_gate_ok": bool_field(divergence_lookup[seed_name], "divergence_gate_ok"),
                    "primary_track_inherited_ok": inherited_track_ok(formal_row, plan.primary_source),
                    "holdout_track_inherited_ok": inherited_track_ok(formal_row, plan.holdout_source),
                    "decoy_track_inherited_ok": inherited_track_ok(formal_row, plan.decoy_source),
                    "inherited_validation_ok": (
                        bool_field(formal_row, "golden_ok")
                        and bool_field(formal_row, "reachability_gate_ok")
                        and bool_field(hardness_lookup[seed_name], "hardness_ok")
                        and bool_field(divergence_lookup[seed_name], "divergence_gate_ok")
                        and inherited_track_ok(formal_row, plan.primary_source)
                        and inherited_track_ok(formal_row, plan.holdout_source)
                        and inherited_track_ok(formal_row, plan.decoy_source)
                    ),
                }
            )

    if len(new_rows) != 40:
        raise RuntimeError(f"Expected 40 new temporal variants, built {len(new_rows)}")
    return new_manifest, new_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a scale160 OpenTitan-only temporal-boosted benchmark root by copying the "
            "current scale120 dataset and appending 40 temporal_cross_cycle bootstrap variants."
        )
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--formal-golden-csv", type=Path, default=DEFAULT_FORMAL_GOLDEN)
    parser.add_argument("--hardness-csv", type=Path, default=DEFAULT_HARDNESS)
    parser.add_argument("--divergence-csv", type=Path, default=DEFAULT_DIVERGENCE)
    parser.add_argument("--skip-copy-base", action="store_true", help="Assume --output-root already contains a copy of the source root.")
    parser.add_argument("--skip-prepare-prompts", action="store_true", help="Do not regenerate experiment/prompt assets after case creation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    formal_lookup = read_csv_lookup(args.formal_golden_csv.resolve())
    hardness_lookup = read_csv_lookup(args.hardness_csv.resolve())
    divergence_lookup = read_csv_lookup(args.divergence_csv.resolve())

    if not args.skip_copy_base:
        if output_root.exists():
            shutil.rmtree(output_root)
        shutil.copytree(source_root, output_root)
    elif not output_root.exists():
        raise FileNotFoundError(f"--skip-copy-base was set but output root does not exist: {output_root}")

    manifest, inherited_rows = create_variants(
        source_root=source_root,
        output_root=output_root,
        formal_lookup=formal_lookup,
        hardness_lookup=hardness_lookup,
        divergence_lookup=divergence_lookup,
    )
    write_manifest(output_root, manifest)

    if not args.skip_prepare_prompts:
        run_prepare_prompt_assets(output_root)

    out_csv = output_root / "temporal_variant_inherited_validation.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(inherited_rows[0].keys()))
        writer.writeheader()
        writer.writerows(inherited_rows)

    summary = {
        "source_root": str(source_root),
        "output_root": str(output_root),
        "base_case_count": 120,
        "new_temporal_variant_count": 40,
        "independent_parent_bug_count": len(TEMPORAL_SEED_NAMES),
        "total_case_count": len(manifest),
        "bug_class_counts": {
            "combination_same_cycle": sum(1 for item in manifest if item.get("bug_class") == "combination_same_cycle"),
            "temporal_cross_cycle": sum(1 for item in manifest if item.get("bug_class") == "temporal_cross_cycle"),
        },
        "all_inherited_validation_ok": all(bool(row["inherited_validation_ok"]) for row in inherited_rows),
        "new_case_names": [row["case_name"] for row in inherited_rows],
        "parent_bug_trace_variants": {
            seed_name: [
                row["case_name"]
                for row in inherited_rows
                if row["parent_bug_id"] == seed_name
            ]
            for seed_name in TEMPORAL_SEED_NAMES
        },
    }
    write_json(output_root / "temporal_variant_expansion_summary.json", summary)

    print(output_root)
    print(out_csv)
    print(output_root / "temporal_variant_expansion_summary.json")


if __name__ == "__main__":
    main()
