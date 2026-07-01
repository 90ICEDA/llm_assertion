#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List

from real_rtl_case_catalog import load_case_blueprints


ASSERT_INCLUDE_RE = re.compile(r'^\s*`include\s+"prim_assert\.sv"\s*$', re.MULTILINE)


def normalize_sv_text(text: str) -> str:
    text = ASSERT_INCLUDE_RE.sub("", text)
    text = text.replace("prim_count_pkg::Clr", "4'h1")
    text = text.replace("prim_count_pkg::Set", "4'h2")
    text = text.replace("prim_count_pkg::Incr", "4'h4")
    text = text.replace("prim_count_pkg::Decr", "4'h8")
    return text.strip() + "\n"


def canonical_signal_name(name: str) -> str:
    return {
        "clk_i": "clk",
        "rst_ni": "rst_n",
    }.get(name, name)


def canonicalize_assertion_text(text: str) -> str:
    return (
        str(text)
        .replace("@(posedge clk_i)", "@(posedge clk)")
        .replace("!rst_ni", "!rst_n")
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def apply_mutation(text: str, edits: Iterable[Dict[str, str]], case_name: str) -> str:
    out = text
    for idx, edit in enumerate(edits, start=1):
        search = str(edit["search"])
        replace = str(edit["replace"])
        count = out.count(search)
        if count != 1:
            raise ValueError(
                f"{case_name}: mutation #{idx} expected exactly one match, found {count}"
            )
        out = out.replace(search, replace, 1)
    return out


def manifest_entry_from_blueprint(blueprint: Dict[str, object]) -> Dict[str, object]:
    entry = {
        key: value
        for key, value in blueprint.items()
        if key
        not in {
            "source_files",
            "top_file",
            "mutation_edits",
        }
    }
    entry["key_signals"] = [canonical_signal_name(str(item)) for item in blueprint["key_signals"]]
    golden = dict(entry.get("golden_sva", {}))
    if golden.get("sva"):
        golden["sva"] = canonicalize_assertion_text(str(golden["sva"]))
    entry["golden_sva"] = golden
    entry["loose_negative_controls"] = [
        {
            **item,
            "sva": canonicalize_assertion_text(str(item["sva"])),
        }
        for item in blueprint.get("loose_negative_controls", [])
    ]
    entry["dataset_phase"] = "real_rtl_mutation_scaffold"
    entry["status"] = "needs_tb_and_waveforms"
    entry["dut_top_module"] = wrapper_module_name(str(blueprint["name"]))
    return entry


def wrapper_module_name(case_name: str) -> str:
    return "dut_" + re.sub(r"[^A-Za-z0-9_]", "_", case_name)


def build_wrapper_module(case_name: str, blueprint: Dict[str, object]) -> str:
    wrapper_name = wrapper_module_name(case_name)
    source_module = str(blueprint["source_module"])

    if source_module == "prim_onehot_check":
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic [3:0] oh_i,
  input logic [1:0] addr_i,
  input logic en_i,
  output logic err_o
);
  prim_onehot_check #(
    .AddrWidth(2),
    .OneHotWidth(4),
    .AddrCheck(1),
    .EnableCheck(1),
    .StrictCheck(1),
    .EnableAlertTriggerSVA(0)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .oh_i(oh_i),
    .addr_i(addr_i),
    .en_i(en_i),
    .err_o(err_o)
  );
endmodule
"""

    if source_module == "prim_reg_we_check":
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic [3:0] oh_i,
  input logic en_i,
  output logic err_o
);
  prim_reg_we_check #(
    .OneHotWidth(4)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .oh_i(oh_i),
    .en_i(en_i),
    .err_o(err_o)
  );
endmodule
"""

    if source_module == "prim_arbiter_fixed":
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic [3:0] req_i,
  input logic ready_i,
  output logic [3:0] gnt_o,
  output logic [1:0] idx_o,
  output logic valid_o
);
  logic [7:0] data_i [4];
  logic [7:0] data_o_unused;

  always_comb begin
    data_i[0] = 8'h10;
    data_i[1] = 8'h20;
    data_i[2] = 8'h40;
    data_i[3] = 8'h80;
  end

  prim_arbiter_fixed #(
    .N(4),
    .DW(8),
    .EnDataPort(1)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .req_i(req_i),
    .data_i(data_i),
    .gnt_o(gnt_o),
    .idx_o(idx_o),
    .valid_o(valid_o),
    .data_o(data_o_unused),
    .ready_i(ready_i)
  );
endmodule
"""

    if source_module == "prim_fifo_sync_cnt":
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic clr_i,
  input logic incr_wptr_i,
  input logic incr_rptr_i,
  output logic [1:0] wptr_o,
  output logic [1:0] rptr_o,
  output logic full_o,
  output logic empty_o,
  output logic [2:0] depth_o,
  output logic err_o
);
  prim_fifo_sync_cnt #(
    .Depth(4),
    .Secure(1'b0),
    .NeverClears(1'b0)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .clr_i(clr_i),
    .incr_wptr_i(incr_wptr_i),
    .incr_rptr_i(incr_rptr_i),
    .wptr_o(wptr_o),
    .rptr_o(rptr_o),
    .full_o(full_o),
    .empty_o(empty_o),
    .depth_o(depth_o),
    .err_o(err_o)
  );
endmodule
"""

    if source_module == "prim_intr_hw":
        bug_family_lower = str(blueprint["bug_family"]).lower()
        intr_t = '"Status"' if ("status" in bug_family_lower or "test_pulse" in bug_family_lower) else '"Event"'
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic event_intr_i,
  input logic reg2hw_intr_enable_q_i,
  input logic reg2hw_intr_test_q_i,
  input logic reg2hw_intr_test_qe_i,
  input logic reg2hw_intr_state_q_i,
  output logic hw2reg_intr_state_de_o,
  output logic hw2reg_intr_state_d_o,
  output logic intr_o
);
  prim_intr_hw #(
    .Width(1),
    .FlopOutput(1),
    .IntrT({intr_t})
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .event_intr_i(event_intr_i),
    .reg2hw_intr_enable_q_i(reg2hw_intr_enable_q_i),
    .reg2hw_intr_test_q_i(reg2hw_intr_test_q_i),
    .reg2hw_intr_test_qe_i(reg2hw_intr_test_qe_i),
    .reg2hw_intr_state_q_i(reg2hw_intr_state_q_i),
    .hw2reg_intr_state_de_o(hw2reg_intr_state_de_o),
    .hw2reg_intr_state_d_o(hw2reg_intr_state_d_o),
    .intr_o(intr_o)
  );
endmodule
"""

    if source_module == "prim_edge_detector":
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic d_i,
  output logic q_sync_o,
  output logic q_posedge_pulse_o,
  output logic q_negedge_pulse_o
);
  prim_edge_detector #(
    .Width(1),
    .ResetValue(1'b0),
    .EnSync(1'b0)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .d_i(d_i),
    .q_sync_o(q_sync_o),
    .q_posedge_pulse_o(q_posedge_pulse_o),
    .q_negedge_pulse_o(q_negedge_pulse_o)
  );
endmodule
"""

    if source_module == "prim_filter":
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic enable_i,
  input logic filter_i,
  output logic filter_o
);
  prim_filter #(
    .AsyncOn(1'b0),
    .Cycles(2)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .enable_i(enable_i),
    .filter_i(filter_i),
    .filter_o(filter_o)
  );
endmodule
"""

    if source_module == "prim_filter_ctr":
        if case_name == "case122_prim_filter_ctr_streak_reset_ignored":
            return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic enable_i,
  input logic filter_i,
  input logic [1:0] thresh_i,
  output logic filter_o,
  output logic second_new_sample_dbg
);
  logic last_filter_i_q;
  logic saw_first_new_sample_q;
  logic run_opposes_output_q;

  prim_filter_ctr #(
    .AsyncOn(1'b0),
    .CntWidth(2)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .enable_i(enable_i),
    .filter_i(filter_i),
    .thresh_i(thresh_i),
    .filter_o(filter_o)
  );

  assign second_new_sample_dbg = enable_i && (thresh_i == 2'd2) &&
                                 (filter_i == last_filter_i_q) &&
                                 saw_first_new_sample_q &&
                                 run_opposes_output_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      last_filter_i_q <= 1'b0;
      saw_first_new_sample_q <= 1'b0;
      run_opposes_output_q <= 1'b0;
    end else begin
      if (!enable_i || (thresh_i != 2'd2)) begin
        saw_first_new_sample_q <= 1'b0;
        run_opposes_output_q <= 1'b0;
      end else if (filter_i != last_filter_i_q) begin
        saw_first_new_sample_q <= 1'b1;
        run_opposes_output_q <= (filter_i != filter_o);
      end else begin
        saw_first_new_sample_q <= 1'b0;
      end
      last_filter_i_q <= filter_i;
    end
  end
endmodule
"""
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic enable_i,
  input logic filter_i,
  input logic [1:0] thresh_i,
  output logic filter_o
);
  prim_filter_ctr #(
    .AsyncOn(1'b0),
    .CntWidth(2)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .enable_i(enable_i),
    .filter_i(filter_i),
    .thresh_i(thresh_i),
    .filter_o(filter_o)
  );
endmodule
"""

    if source_module == "prim_count":
        return f"""module {wrapper_name} (
  input logic clk,
  input logic rst_n,
  input logic clr_i,
  input logic set_i,
  input logic [3:0] set_cnt_i,
  input logic incr_en_i,
  input logic decr_en_i,
  input logic [3:0] step_i,
  input logic commit_i,
  output logic [3:0] cnt_o,
  output logic [3:0] cnt_after_commit_o,
  output logic err_o
);
  prim_count #(
    .Width(4),
    .ResetValue(4'h0),
    .EnableAlertTriggerSVA(0)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .clr_i(clr_i),
    .set_i(set_i),
    .set_cnt_i(set_cnt_i),
    .incr_en_i(incr_en_i),
    .decr_en_i(decr_en_i),
    .step_i(step_i),
    .commit_i(commit_i),
    .cnt_o(cnt_o),
    .cnt_after_commit_o(cnt_after_commit_o),
    .err_o(err_o)
  );
endmodule
"""

    raise ValueError(f"Unsupported wrapper source module: {source_module}")


def build_case(
    repo_root: Path,
    output_root: Path,
    blueprint: Dict[str, object],
) -> Dict[str, object]:
    case_name = str(blueprint["name"])
    source_files = [repo_root / "external" / "opentitan" / rel for rel in blueprint["source_files"]]
    top_file = repo_root / "external" / "opentitan" / str(blueprint["top_file"])
    case_dir = output_root / case_name
    case_dir.mkdir(parents=True, exist_ok=True)

    source_text_by_path: Dict[Path, str] = {}
    for source_path in source_files:
        source_text_by_path[source_path] = normalize_sv_text(read_text(source_path))

    top_text = normalize_sv_text(read_text(top_file))
    buggy_top = apply_mutation(top_text, blueprint["mutation_edits"], case_name)
    wrapper_text = build_wrapper_module(case_name, blueprint)

    ordered_parts_correct: List[str] = []
    ordered_parts_buggy: List[str] = []
    for source_path in source_files:
        banner = f"// ----- source: {source_path.as_posix()} -----\n"
        if source_path == top_file:
            ordered_parts_correct.append(banner + top_text)
            ordered_parts_buggy.append(f"// ----- mutated source: {source_path.as_posix()} -----\n" + buggy_top)
        else:
            ordered_parts_correct.append(banner + source_text_by_path[source_path])
            ordered_parts_buggy.append(banner + source_text_by_path[source_path])

    header = (
        "// Auto-generated real RTL mutation scaffold.\n"
        f"// case: {case_name}\n"
        f"// source_project: {blueprint['source_project']}\n"
        f"// source_module: {blueprint['source_module']}\n\n"
        "`ifndef ASSERT_DEFAULT_CLK\n`define ASSERT_DEFAULT_CLK clk_i\n`endif\n"
        "`ifndef ASSERT_DEFAULT_RST\n`define ASSERT_DEFAULT_RST !rst_ni\n`endif\n"
        "`ifndef ASSERT_I\n`define ASSERT_I(__name, __prop)\n`endif\n"
        "`ifndef ASSERT_INIT\n`define ASSERT_INIT(__name, __prop)\n`endif\n"
        "`ifndef ASSERT_INIT_NET\n`define ASSERT_INIT_NET(__name, __prop)\n`endif\n"
        "`ifndef ASSERT_FINAL\n`define ASSERT_FINAL(__name, __prop)\n`endif\n"
        "`ifndef ASSERT_AT_RESET\n`define ASSERT_AT_RESET(__name, __prop, __rst = `ASSERT_DEFAULT_RST)\n`endif\n"
        "`ifndef ASSERT_AT_RESET_AND_FINAL\n`define ASSERT_AT_RESET_AND_FINAL(__name, __prop, __rst = `ASSERT_DEFAULT_RST)\n`endif\n"
        "`ifndef ASSERT\n`define ASSERT(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)\n`endif\n"
        "`ifndef ASSERT_NEVER\n`define ASSERT_NEVER(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)\n`endif\n"
        "`ifndef ASSERT_KNOWN\n`define ASSERT_KNOWN(__name, __sig, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)\n`endif\n"
        "`ifndef COVER\n`define COVER(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)\n`endif\n"
        "`ifndef ASSUME\n`define ASSUME(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)\n`endif\n"
        "`ifndef ASSUME_I\n`define ASSUME_I(__name, __prop)\n`endif\n"
        "`ifndef ASSUME_FPV\n`define ASSUME_FPV(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)\n`endif\n\n"
    )

    correct_text = header + wrapper_text + "\n" + "\n".join(ordered_parts_correct)
    buggy_text = header + wrapper_text + "\n" + "\n".join(ordered_parts_buggy)

    write_text(case_dir / "correct.v", correct_text)
    write_text(case_dir / "buggy.v", buggy_text)
    write_text(
        case_dir / "STIMULUS_NOTES.md",
        "\n".join(
            [
                f"# {case_name}",
                "",
                f"- `bug_class`: {blueprint['bug_class']}",
                f"- `bug_family`: {blueprint['bug_family']}",
                f"- `bug_type`: {blueprint['bug_type']}",
                "",
                "## Spec",
                "",
                str(blueprint["spec"]),
                "",
                "## Hardness Rationale",
                "",
                str(blueprint["hard_case_rationale"]),
                "",
                "## Stimulus Notes",
                "",
                str(blueprint["stimulus_notes"]),
                "",
                "## Loose Negative Controls",
                "",
            ]
            + [
                f"- `{item['name']}`: {item['why_it_should_miss']}\n  Assertion: `{item['sva']}`"
                for item in blueprint.get("loose_negative_controls", [])
            ]
            + [
                "",
                "## Next Step",
                "",
                "Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.",
                "",
            ]
        ),
    )

    return manifest_entry_from_blueprint(blueprint)


def write_manifest(output_root: Path, entries: List[Dict[str, object]]) -> None:
    manifest = {"cases": entries}
    write_text(
        output_root / "case_manifest.json",
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    )


def write_readme(output_root: Path, entries: List[Dict[str, object]]) -> None:
    combo = sum(1 for entry in entries if entry.get("bug_class") == "combination_same_cycle")
    temporal = sum(1 for entry in entries if entry.get("bug_class") == "temporal_cross_cycle")
    lines = [
        "# Real RTL Mutation Scaffold",
        "",
        "This directory contains mutation-backed case scaffolds extracted from real OpenTitan RTL.",
        "The old evaluator scripts can be pointed at this root once each case has:",
        "",
        "- `tb.v`",
        "- `tb_holdout.v`",
        "- waveform CSV/VCD files",
        "- prompt assets regenerated",
        "- golden + hardness self-checks passing",
        "",
        f"- total scaffolds: {len(entries)}",
        f"- combo/same-cycle scaffolds: {combo}",
        f"- temporal/cross-cycle scaffolds: {temporal}",
        "",
        "Important: these are source-materialized mutation plans, not yet admitted benchmark cases.",
        "Use the per-case `STIMULUS_NOTES.md` files to finish the held-out stimuli and waveform generation.",
        "",
    ]
    write_text(output_root / "README.md", "\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize real-RTL mutation scaffolds from the planning catalog."
    )
    parser.add_argument(
        "--repo-root",
        default="..",
        help="Path to the repository root relative to this script (default: ..).",
    )
    parser.add_argument(
        "--output-root",
        default="../rtl_cases_real",
        help="Output root for the new real-RTL scaffold dataset.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = (script_dir / args.repo_root).resolve()
    output_root = (script_dir / args.output_root).resolve()
    blueprints = [blueprint for blueprint in load_case_blueprints() if not blueprint.get("disabled")]

    entries = [build_case(repo_root, output_root, blueprint) for blueprint in blueprints]
    write_manifest(output_root, entries)
    write_readme(output_root, entries)
    print(f"[DONE] Materialized {len(entries)} real RTL mutation scaffolds at {output_root}")


if __name__ == "__main__":
    main()
