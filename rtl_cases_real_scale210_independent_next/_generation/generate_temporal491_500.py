#!/usr/bin/env python3
"""Generate the sealed-source candidate assets for temporal cases 491--500.

The generated cases remain pending until the WSL semantic and procedural-monitor
gates are run.  This file is kept beside the candidates as construction provenance.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AXIS_COMMIT = "48ff7a7e2ef782cf778d47910cf85835c64b1bce"
CC_COMMIT = "03d98106aa19952a10360d2230def85144a0008b"


CASES = [
    dict(num=491, slug="axis_pipeline_register_valid_latency", project="verilog_axis", module="axis_pipeline_register",
         source="external/verilog-axis/rtl/axis_pipeline_register.v", family="three_stage_valid_bypassed",
         temporal="exact three-cycle ready/valid pipeline latency", trigger="s_valid_i", aux="ready_i",
         spec="An accepted input valid traverses all three registered stages. It must not be observable at q_o after only two sampling edges.",
         golden="$rose(s_valid_i) |-> ##2 !q_o",
         body="""  reg [2:0] valid_pipe;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) valid_pipe <= 3'b000;
    else if (ready_i) valid_pipe <= {valid_pipe[1:0],s_valid_i};
  assign q_o = valid_pipe[{tap}];
  assign state_o = {5'b0,valid_pipe};
""", good="2", bad="1"),
    dict(num=492, slug="axis_async_fifo_gray_visibility", project="verilog_axis", module="axis_async_fifo",
         source="external/verilog-axis/rtl/axis_async_fifo.v", family="gray_pointer_sync_stage_removed",
         temporal="three-stage CDC pointer visibility latency", trigger="write_toggle_i", aux="sample_enable_i",
         spec="A write-toggle crossing into the read domain becomes visible only after all three synchronizer stages; the second-stage value is not externally visible.",
         golden="$rose(write_toggle_i) |-> ##2 !q_o",
         body="""  reg [2:0] sync_pipe;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) sync_pipe <= 3'b000;
    else if (sample_enable_i) sync_pipe <= {sync_pipe[1:0],write_toggle_i};
  assign q_o = sync_pipe[{tap}];
  assign state_o = {5'b0,sync_pipe};
""", good="2", bad="1"),
    dict(num=493, slug="axis_stat_counter_frame_commit_delay", project="verilog_axis", module="axis_stat_counter",
         source="external/verilog-axis/rtl/axis_stat_counter.v", family="frame_count_committed_same_cycle",
         temporal="deferred frame-count commit after terminal handshake", trigger="frame_end_i", aux="ready_i",
         spec="A terminal transfer first records a pending frame event. The public frame counter commits on the following clock, never in the terminal-transfer clock itself.",
         golden="($rose(frame_end_i) && valid_i && ready_i) |=> (q_o == $past(q_o))",
         ports="input wire valid_i,", tb_extra="reg valid_i=0;",
         body="""  reg pending;
  reg [7:0] count;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin pending<=0; count<=0; end
    else begin
      pending <= frame_end_i && valid_i && ready_i;
      if ({condition}) count <= count + 1'b1;
    end
  end
  assign q_o = count[0];
  assign state_o = count;
""", good="pending", bad="frame_end_i && valid_i && ready_i"),
    dict(num=494, slug="axis_ram_switch_response_pipeline", project="verilog_axis", module="axis_ram_switch",
         source="external/verilog-axis/rtl/axis_ram_switch.v", family="response_pipeline_stage_skipped",
         temporal="three-stage arbitration response latency", trigger="grant_i", aux="output_ready_i",
         spec="A granted RAM-switch command traverses three registered arbitration stages. Response valid cannot rise at the two-cycle observation point.",
         golden="$rose(grant_i) |-> ##2 !q_o",
         body="""  reg [2:0] response_pipe;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) response_pipe <= 3'b000;
    else if (output_ready_i) response_pipe <= {response_pipe[1:0],grant_i};
  assign q_o = response_pipe[{tap}];
  assign state_o = {5'b0,response_pipe};
""", good="2", bad="1"),
    dict(num=495, slug="axis_fifo_adapter_commit_pulse_width", project="verilog_axis", module="axis_fifo_adapter",
         source="external/verilog-axis/rtl/axis_fifo_adapter.v", family="adapter_commit_pulse_stretched",
         temporal="single-cycle width-adapter commit pulse", trigger="delimiter_i", aux="output_ready_i",
         spec="Accepting the final segment of an adapted word produces exactly one registered commit-valid cycle. The valid pulse must be low two samples after the boundary trigger.",
         golden="$rose(delimiter_i) |-> ##2 !q_o",
         body="""  reg valid_reg;
  reg hold_reg;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin valid_reg<=0; hold_reg<=0; end
    else if (output_ready_i) begin
      valid_reg <= delimiter_i | {stretch};
      hold_reg <= delimiter_i;
    end
  end
  assign q_o = valid_reg;
  assign state_o = {6'b0,hold_reg,valid_reg};
""", good="1'b0", bad="hold_reg"),
    dict(num=496, slug="cc_stream_throttle_release_early", project="common_cells", module="cc_stream_throttle",
         source="external/common_cells/src/cc_stream_throttle.sv", family="throttle_counter_loaded_one_short",
         temporal="exact stream-throttle release interval", trigger="start_i", aux="enable_i",
         spec="Starting a throttle interval suppresses release for three cycles. No release pulse is permitted at the two-cycle observation point; release occurs only after the full interval.",
         golden="$rose(start_i) |-> ##2 !q_o",
         body="""  reg [2:0] count;
  reg retry;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin count<=0; retry<=0; end
    else if (enable_i) begin
      retry <= (count == 1);
      if (start_i) count <= {load};
      else if (count != 0) count <= count - 1'b1;
    end
  end
  assign q_o = retry;
  assign state_o = {5'b0,count};
""", good="3", bad="2"),
    dict(num=497, slug="cc_cdc_4phase_ack_sync_depth", project="common_cells", module="cc_cdc_4phase",
         source="external/common_cells/src/cc_cdc_4phase.sv", family="ack_synchronizer_stage_removed",
         temporal="three-stage four-phase acknowledgement synchronization", trigger="async_ack_i", aux="sample_enable_i",
         spec="The asynchronous acknowledgement passes through three destination-clock registers before it is exposed. A two-stage observation is forbidden.",
         golden="$rose(async_ack_i) |-> ##2 !q_o",
         body="""  reg [2:0] ack_sync;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) ack_sync <= 3'b000;
    else if (sample_enable_i) ack_sync <= {ack_sync[1:0],async_ack_i};
  assign q_o = ack_sync[{tap}];
  assign state_o = {5'b0,ack_sync};
""", good="2", bad="1"),
    dict(num=498, slug="cc_serial_deglitch_qualification_short", project="common_cells", module="cc_serial_deglitch",
         source="external/common_cells/src/cc_serial_deglitch.sv", family="qualification_count_reduced",
         temporal="three-consecutive-sample glitch qualification", trigger="noisy_i", aux="sample_enable_i",
         spec="A high input is accepted only after three consecutive enabled samples. Two high samples are insufficient to raise the filtered output.",
         golden="$rose(noisy_i) |-> ##2 !q_o",
         body="""  reg [1:0] high_count;
  reg filtered;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin high_count<=0; filtered<=0; end
    else if (sample_enable_i) begin
      if (!noisy_i) begin high_count<=0; filtered<=0; end
      else begin
        if (high_count != 3) high_count <= high_count + 1'b1;
        if (high_count >= {threshold}) filtered <= 1'b1;
      end
    end
  end
  assign q_o = filtered;
  assign state_o = {6'b0,high_count};
""", good="2", bad="1"),
    dict(num=499, slug="cc_shift_reg_gated_stage_bypass", project="common_cells", module="cc_shift_register_gated",
         source="external/common_cells/src/cc_shift_register_gated.sv", family="enabled_shift_stage_bypassed",
         temporal="three accepted-shift data latency", trigger="data_i", aux="enable_i",
         spec="With enable asserted, serial data traverses all three shift stages. A newly asserted input bit must not reach q_o after only two enabled sampling edges.",
         golden="($rose(data_i) && enable_i) |-> ##2 !q_o",
         body="""  reg [2:0] shift_reg;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) shift_reg <= 3'b000;
    else if (enable_i) shift_reg <= {shift_reg[1:0],data_i};
  assign q_o = shift_reg[{tap}];
  assign state_o = {5'b0,shift_reg};
""", good="2", bad="1"),
    dict(num=500, slug="cc_isochronous_handshake_early_drop", project="common_cells", module="cc_isochronous_4phase_handshake",
         source="external/common_cells/src/cc_isochronous_4phase_handshake.sv", family="request_drops_on_unsynchronized_ack",
         temporal="synchronized four-phase request release ordering", trigger="ack_i", aux="start_i",
         spec="Once started, the request remains asserted until acknowledgement has crossed two synchronization stages. A raw asynchronous acknowledgement cannot release the request.",
         golden="$rose(ack_i) |=> q_o",
         body="""  reg ack_meta,ack_sync,req;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin ack_meta<=0; ack_sync<=0; req<=0; end
    else begin
      ack_meta <= ack_i;
      ack_sync <= ack_meta;
      if (start_i) req <= 1'b1;
      else if ({ack_condition}) req <= 1'b0;
    end
  end
  assign q_o = req;
  assign state_o = {5'b0,ack_sync,ack_meta,req};
""", good="ack_sync", bad="ack_i"),
]


def identifiers(case: dict) -> tuple[str, str]:
    trigger = case["trigger"]
    aux = case["aux"]
    return trigger, aux


def rtl(case: dict, mutation: bool) -> str:
    trigger, aux = identifiers(case)
    extra_port = case.get("ports", "")
    body = case["body"]
    key = case["bad"] if mutation else case["good"]
    if "{tap}" in body:
        body = body.replace("{tap}", key)
    elif "{condition}" in body:
        body = body.replace("{condition}", key)
    elif "{stretch}" in body:
        body = body.replace("{stretch}", key)
    elif "{load}" in body:
        body = body.replace("{load}", key)
    elif "{threshold}" in body:
        body = body.replace("{threshold}", key)
    elif "{ack_condition}" in body:
        body = body.replace("{ack_condition}", key)
    return f"""`timescale 1ns/1ps
module {case['module']}(
  input wire clk_i,
  input wire rst_ni,
  input wire {trigger},
  input wire {aux},
  {extra_port}
  output wire q_o,
  output wire [7:0] state_o
);
{body}endmodule
"""


def tb(case: dict, variant: int) -> str:
    trigger, aux = identifiers(case)
    extra = case.get("tb_extra", "")
    # Different idle padding and pulse spacing give three non-identical traces.
    wait = (8, 18, 28)[variant]
    # A one-clock trigger avoids creating several obligations from a level;
    # the variants differ in idle prefix and therefore still yield distinct traces.
    hold = 10
    trigger_setup = f"{trigger}=1; {aux}=1;"
    if case["num"] == 493:
        trigger_setup += " valid_i=1;"
    if case["num"] in (498, 499):
        # These qualifications require a sustained level while still exposing
        # the premature second-sample response in the buggy RTL.
        hold = 35
    if case["num"] == 500:
        # Start request first, then assert acknowledgement asynchronously.
        stimulus = f"#{wait} start_i=1; #10 start_i=0; #{hold} ack_i=1; #20 ack_i=0;"
    else:
        stimulus = f"#{wait} {trigger_setup} #{hold} {trigger}=0; #10 {aux}=0;"
        if case["num"] == 493:
            stimulus += " valid_i=0;"
    return f"""`timescale 1ns/1ps
module tb;
  reg clk_i=0;
  always #5 clk_i=~clk_i;
  reg rst_ni=0;
  reg {trigger}=0;
  reg {aux}=0;
  {extra}
  wire q_o;
  wire [7:0] state_o;
  {case['module']} dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1;
    {stimulus}
    #90 $finish;
  end
endmodule
"""


def weak_assets(case: dict) -> tuple[str, dict]:
    trigger, aux = identifiers(case)
    props = [
        ("W1_single_cycle_implication", "single_cycle_implication", f"{trigger} |-> ({trigger} == {trigger})", trigger, True,
         "Checks only the trigger level and ignores the delayed response."),
        ("W2_final_output_only", "final_output_only", "1'b1 |-> !$isunknown(q_o)", "1'b1", True,
         "Knownness of the final output does not constrain response timing."),
        ("W3_delay_removed", "delay_removed", f"{aux} |-> (q_o == q_o)", aux, True,
         "Removing the delay turns the response check into a tautology."),
        ("W4_antecedent_removed", "antecedent_removed", "q_o == q_o", None, False,
         "Dropping the trigger loses the causal obligation."),
        ("W5_simple_invariant", "simple_invariant", "state_o <= 8'hff", None, False,
         "A range invariant cannot distinguish the temporal mutation."),
    ]
    sva = "\n".join(f"assert property (@(posedge clk_i) disable iff (!rst_ni) ({p}));" for _, _, p, _, _, _ in props) + "\n"
    doc = {
        "schema_version": "weak-assertions-v1", "case_id": f"case{case['num']}_{case['slug']}",
        "parent_bug_id": f"case{case['num']}_{case['slug']}", "source_project": case["project"],
        "admission_rule": "At least two non-vacuous weak assertions must miss the RTL bug.",
        "overall_validation_status": "pending",
        "assertions": [
            {"id": i, "weakness_class": kind, "property": p, "antecedent": ant,
             "antecedent_nonempty": nonempty, "expected_weakness": why,
             "validation_status": "pending", "catches_bug": None, "nonvacuity_verified": False}
            for i, kind, p, ant, nonempty, why in props
        ],
    }
    return sva, doc


for case in CASES:
    name = f"case{case['num']}_{case['slug']}"
    directory = ROOT / name
    directory.mkdir(parents=True, exist_ok=True)
    correct = rtl(case, False)
    buggy = rtl(case, True)
    (directory / "correct.v").write_text(correct, encoding="utf-8")
    (directory / "buggy.v").write_text(buggy, encoding="utf-8")
    diff = "".join(difflib.unified_diff(correct.splitlines(True), buggy.splitlines(True), fromfile="correct.v", tofile="buggy.v"))
    (directory / "mutation.diff").write_text(diff, encoding="utf-8")
    (directory / "spec.md").write_text(case["spec"] + "\n", encoding="utf-8")
    (directory / "golden.sva").write_text(
        f"assert property (@(posedge clk_i) disable iff (!rst_ni) ({case['golden']}));\n", encoding="utf-8")
    for filename, variant in (("tb.v", 0), ("tb_holdout.v", 1), ("tb_decoy.v", 2)):
        (directory / filename).write_text(tb(case, variant), encoding="utf-8")
    weak_sva, weak_json = weak_assets(case)
    (directory / "weak_assertions.sva").write_text(weak_sva, encoding="utf-8")
    (directory / "weak_assertions.json").write_text(json.dumps(weak_json, indent=2) + "\n", encoding="utf-8")
    commit = AXIS_COMMIT if case["project"] == "verilog_axis" else CC_COMMIT
    metadata = {
        "name": name, "parent_bug_id": name, "source_project": case["project"],
        "source_url": "https://github.com/alexforencich/verilog-axis.git" if case["project"] == "verilog_axis" else "https://github.com/pulp-platform/common_cells.git",
        "source_commit": commit, "source_module": case["module"], "source_files": [case["source"]],
        "bug_class": "temporal_cross_cycle", "bug_family": case["family"],
        "mutation_kind": "actual_rtl_logic_change", "relevant_signals": ["clk_i", "rst_ni", case["trigger"], case["aux"], "q_o", "state_o"],
        "temporal_type": case["temporal"], "status": "pending",
        "golden_sva": {"assertion": f"assert property (@(posedge clk_i) disable iff (!rst_ni) ({case['golden']}));"},
        "trace_variants": ["primary", "heldout", "decoy"],
        "first_divergence": {"primary": None, "heldout": None, "decoy": None},
        "correct_sha256": hashlib.sha256(correct.encode()).hexdigest(),
        "buggy_sha256": hashlib.sha256(buggy.encode()).hexdigest(),
    }
    (directory / "case_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

print(json.dumps({"generated": len(CASES), "range": "case491-case500", "status": "pending"}, indent=2))
