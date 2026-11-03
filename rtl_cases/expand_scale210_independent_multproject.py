#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "rtl_cases_real_scale160_temporal_boosted"
DEFAULT_OUT = ROOT / "rtl_cases_real_scale210_independent"

SOURCE_REVISIONS = {
    "opentitan": {
        "commit": "3d0ce04455d4568c3d140517555ad95db4fb04c8",
        "url": "https://github.com/lowRISC/opentitan.git",
    },
    "common_cells": {
        "commit": "03d98106aa19952a10360d2230def85144a0008b",
        "url": "https://github.com/pulp-platform/common_cells.git",
    },
    "verilog_axis": {
        "commit": "48ff7a7e2ef782cf778d47910cf85835c64b1bce",
        "url": "https://github.com/alexforencich/verilog-axis.git",
    },
}

# Counts are intentionally spread across projects and modules. Each selected
# source line becomes one unique RTL mutation and therefore one parent bug.
TEMPORAL_TARGETS = [
    ("opentitan", "prim_filter", "external/opentitan/hw/ip/prim/rtl/prim_filter.sv", 3),
    ("opentitan", "prim_intr_hw", "external/opentitan/hw/ip/prim/rtl/prim_intr_hw.sv", 2),
    ("opentitan", "prim_fifo_sync_cnt", "external/opentitan/hw/ip/prim/rtl/prim_fifo_sync_cnt.sv", 4),
    ("common_cells", "cc_edge_propagator_ack", "external/common_cells/src/cc_edge_propagator_ack.sv", 2),
    ("common_cells", "cc_edge_propagator_tx", "external/common_cells/src/cc_edge_propagator_tx.sv", 3),
    ("common_cells", "cc_rstgen_bypass", "external/common_cells/src/cc_rstgen_bypass.sv", 2),
    ("common_cells", "cc_clk_mux_glitch_free", "external/common_cells/src/cc_clk_mux_glitch_free.sv", 2),
    ("common_cells", "cc_clk_int_div", "external/common_cells/src/cc_clk_int_div.sv", 2),
    ("verilog_axis", "axis_register", "external/verilog-axis/rtl/axis_register.v", 3),
    ("verilog_axis", "axis_fifo", "external/verilog-axis/rtl/axis_fifo.v", 3),
    ("verilog_axis", "arbiter", "external/verilog-axis/rtl/arbiter.v", 2),
    ("verilog_axis", "axis_rate_limit", "external/verilog-axis/rtl/axis_rate_limit.v", 2),
]

COMBINATION_TARGETS = [
    ("opentitan", "prim_onehot_check", "external/opentitan/hw/ip/prim/rtl/prim_onehot_check.sv", 2),
    ("opentitan", "prim_edge_detector", "external/opentitan/hw/ip/prim/rtl/prim_edge_detector.sv", 2),
    ("opentitan", "prim_filter_ctr", "external/opentitan/hw/ip/prim/rtl/prim_filter_ctr.sv", 2),
    ("common_cells", "cc_fifo", "external/common_cells/src/cc_fifo.sv", 2),
    ("common_cells", "cc_onehot", "external/common_cells/src/cc_onehot.sv", 2),
    ("common_cells", "cc_stream_mux", "external/common_cells/src/cc_stream_mux.sv", 2),
    ("common_cells", "cc_lzc", "external/common_cells/src/cc_lzc.sv", 2),
    ("verilog_axis", "priority_encoder", "external/verilog-axis/rtl/priority_encoder.v", 2),
    ("verilog_axis", "axis_mux", "external/verilog-axis/rtl/axis_mux.v", 2),
    ("verilog_axis", "axis_demux", "external/verilog-axis/rtl/axis_demux.v", 2),
]

SEQ_RE = re.compile(r"^(\s*)([A-Za-z_][\w$]*(?:\s*\[[^\]]+\])?)\s*<=\s*(.+);\s*$")
ASSIGN_RE = re.compile(r"^(\s*)assign\s+([A-Za-z_][\w$]*(?:\s*\[[^\]]+\])?)\s*=\s*(.+);\s*$")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sequential_candidates(lines: list[str]) -> list[tuple[int, str, str, str]]:
    out = []
    for index, line in enumerate(lines):
        code = line.split("//", 1)[0].rstrip()
        match = SEQ_RE.match(code)
        if not match:
            continue
        indent, lhs, rhs = match.groups()
        if rhs.strip() == lhs.strip() or "<=" in rhs or rhs.strip().startswith("#"):
            continue
        replacement = f"{indent}{lhs} <= {lhs}; // ASSERTIONFORGE_MUTATION: state update suppressed\n"
        out.append((index, line, replacement, lhs.strip()))
    return out


def assign_candidates(lines: list[str]) -> list[tuple[int, str, str, str]]:
    out = []
    for index, line in enumerate(lines):
        code = line.split("//", 1)[0].rstrip()
        match = ASSIGN_RE.match(code)
        if not match:
            continue
        indent, lhs, rhs = match.groups()
        if rhs.strip() in {"'0", "1'b0", "0"}:
            continue
        replacement = f"{indent}assign {lhs} = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed\n"
        out.append((index, line, replacement, lhs.strip()))
    return out


def make_cases(targets: list[tuple[str, str, str, int]], bug_class: str, start_number: int) -> list[dict]:
    cases = []
    case_number = start_number
    for project, module, rel_path, requested in targets:
        source_path = ROOT / rel_path
        original = source_path.read_text(encoding="utf-8")
        compatibility_edits = []
        # Icarus 12 cannot parse a repeated concatenation containing an array
        # element type cast in cc_fifo's reset value.  `'0` is the equivalent
        # whole-object reset value accepted by both Icarus and synthesis tools.
        if rel_path == "external/common_cells/src/cc_fifo.sv":
            old = "{FifoDepth{data_t'('0)}}"
            new = "'0"
            if old not in original:
                raise RuntimeError(f"Expected cc_fifo compatibility expression not found: {old}")
            original = original.replace(old, new)
            compatibility_edits.append({"search": old, "replace": new, "semantic_change": False})
        lines = original.splitlines(keepends=True)
        candidates = sequential_candidates(lines) if bug_class == "temporal_cross_cycle" else assign_candidates(lines)
        if len(candidates) < requested:
            raise RuntimeError(f"{rel_path}: need {requested} {bug_class} mutation points, found {len(candidates)}")
        for ordinal, (line_index, old_line, new_line, signal) in enumerate(candidates[:requested], start=1):
            mutated_lines = list(lines)
            mutated_lines[line_index] = new_line
            mutated = "".join(mutated_lines)
            case_name = f"case{case_number}_{module}_{'temporal_hold' if bug_class == 'temporal_cross_cycle' else 'protocol_suppress'}_{ordinal}"
            cases.append(
                {
                    "name": case_name,
                    "parent_bug_id": case_name,
                    "source_project": project,
                    "source_url": SOURCE_REVISIONS[project]["url"],
                    "source_commit": SOURCE_REVISIONS[project]["commit"],
                    "source_module": module,
                    "source_files": [rel_path],
                    "top_file": rel_path,
                    "bug_class": bug_class,
                    "bug_family": "sequential_state_update_suppressed" if bug_class == "temporal_cross_cycle" else "combinational_protocol_output_suppressed",
                    "bug_type": f"{signal} state update is suppressed" if bug_class == "temporal_cross_cycle" else f"{signal} combinational/protocol output is forced low",
                    "spec": f"Signal {signal} shall follow the original {module} RTL behavior; the mutation changes the actual RTL implementation at source line {line_index + 1}.",
                    "mutation_edits": [{"line": line_index + 1, "search": old_line.rstrip("\r\n"), "replace": new_line.rstrip("\r\n")}],
                    "mutation_signal": signal,
                    "relevant_signals": [signal],
                    "temporal_type": (
                        "cross-cycle sequential state transition"
                        if bug_class == "temporal_cross_cycle"
                        else "same-cycle combinational/protocol relation"
                    ),
                    "mutation_kind": "sequential_hold" if bug_class == "temporal_cross_cycle" else "combinational_force_zero",
                    "iverilog_compatibility_edits": compatibility_edits,
                    "correct_sha256": sha256(original),
                    "buggy_sha256": sha256(mutated),
                    "correct_text": original,
                    "buggy_text": mutated,
                    "dataset_phase": "scale210_independent_multproject",
                    "status": "rtl_mutation_materialized_validation_pending",
                }
            )
            case_number += 1
    return cases


def validate_cases(cases: list[dict]) -> dict:
    errors = []
    if len(cases) < 50:
        errors.append(f"case_count={len(cases)} < 50")
    temporal = sum(c["bug_class"] == "temporal_cross_cycle" for c in cases)
    combination = sum(c["bug_class"] == "combination_protocol" for c in cases)
    projects = {c["source_project"] for c in cases}
    modules = {(c["source_project"], c["source_module"]) for c in cases}
    signatures = {
        (c["source_files"][0], c["mutation_edits"][0]["line"], c["mutation_edits"][0]["replace"])
        for c in cases
    }
    if temporal < 30:
        errors.append(f"temporal_count={temporal} < 30")
    if combination < 20:
        errors.append(f"combination_protocol_count={combination} < 20")
    if len(projects) < 3:
        errors.append(f"project_count={len(projects)} < 3")
    if len(modules) < 15:
        errors.append(f"module_count={len(modules)} < 15")
    if len(signatures) != len(cases):
        errors.append("duplicate mutation signatures detected")
    for case in cases:
        if case["correct_text"] == case["buggy_text"]:
            errors.append(f"{case['name']}: RTL was not changed")
        if case["parent_bug_id"] != case["name"]:
            errors.append(f"{case['name']}: parent_bug_id is not independent")
    if errors:
        raise RuntimeError("Independent expansion rejected:\n- " + "\n- ".join(errors))
    return {
        "new_independent_bug_count": len(cases),
        "temporal_bug_count": temporal,
        "combination_protocol_bug_count": combination,
        "source_project_count": len(projects),
        "source_projects": sorted(projects),
        "unique_module_count": len(modules),
        "unique_modules": [f"{p}:{m}" for p, m in sorted(modules)],
        "unique_parent_bug_count": len({c["parent_bug_id"] for c in cases}),
        "unique_mutation_signature_count": len(signatures),
        "all_cases_modify_rtl": True,
    }


def materialize_case(output_root: Path, case: dict, *, refresh: bool = False) -> dict:
    target = output_root / case["name"]
    if target.exists() and refresh:
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=False)
    (target / "correct.v").write_text(case["correct_text"], encoding="utf-8", newline="\n")
    (target / "buggy.v").write_text(case["buggy_text"], encoding="utf-8", newline="\n")
    diff = "".join(
        difflib.unified_diff(
            case["correct_text"].splitlines(keepends=True),
            case["buggy_text"].splitlines(keepends=True),
            fromfile="correct.v",
            tofile="buggy.v",
        )
    )
    (target / "rtl_mutation.diff").write_text(diff, encoding="utf-8", newline="\n")
    metadata = {k: v for k, v in case.items() if k not in {"correct_text", "buggy_text"}}
    write_json(target / "case_metadata.json", metadata)
    (target / "STIMULUS_NOTES.md").write_text(
        f"# {case['name']}\n\n"
        f"- Parent bug: `{case['parent_bug_id']}`\n"
        f"- Upstream RTL: `{case['source_files'][0]}`\n"
        f"- Mutation: `{case['mutation_edits'][0]['search']}` → `{case['mutation_edits'][0]['replace']}`\n"
        f"- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.\n",
        encoding="utf-8",
        newline="\n",
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-root", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--skip-copy-base", action="store_true")
    parser.add_argument("--refresh-new-cases", action="store_true")
    args = parser.parse_args()
    base_root = args.base_root.resolve()
    output_root = args.output_root.resolve()
    if not args.skip_copy_base:
        if output_root.exists():
            raise FileExistsError(f"Refusing to overwrite {output_root}")
        shutil.copytree(base_root, output_root)
    elif not output_root.exists():
        raise FileNotFoundError(output_root)

    temporal = make_cases(TEMPORAL_TARGETS, "temporal_cross_cycle", 401)
    combination = make_cases(COMBINATION_TARGETS, "combination_protocol", 431)
    cases = temporal + combination
    summary = validate_cases(cases)

    base_manifest = read_json(base_root / "case_manifest.json")["cases"]
    new_entries = [materialize_case(output_root, case, refresh=args.refresh_new_cases) for case in cases]
    write_json(output_root / "case_manifest.json", {"cases": base_manifest + new_entries})
    write_json(output_root / "independent_expansion_summary.json", summary)
    write_json(output_root / "independent_new_bug_manifest.json", {"cases": new_entries})
    print(output_root)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
