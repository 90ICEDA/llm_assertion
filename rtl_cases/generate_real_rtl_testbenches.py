#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


def load_manifest(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def case_id(case_name: str) -> str:
    return case_name.split("_", 1)[0]


def onehot_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if case_name == "case101_prim_onehot_multihot_suppressed":
        if holdout:
            stimulus = """
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1100; addr_i = 2'd2; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1100; addr_i = 2'd2; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
"""
        else:
            stimulus = """
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd1; @(posedge clk);
"""
    elif case_name in {
        "case102_prim_onehot_enable_mismatch_suppressed",
        "case129_prim_onehot_zero_enabled_suppressed",
    }:
        if holdout:
            stimulus = """
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0000; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0000; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1000; addr_i = 2'd3; @(posedge clk);
"""
        else:
            stimulus = """
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0000; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0000; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0100; addr_i = 2'd2; @(posedge clk);
"""
    elif case_name == "case103_prim_onehot_addr_mismatch_suppressed":
        if holdout:
            stimulus = """
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1000; addr_i = 2'd3; @(posedge clk);
"""
        else:
            stimulus = """
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0100; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0100; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0100; addr_i = 2'd2; @(posedge clk);
"""
    elif case_name == "case137_prim_onehot_addr_false_positive":
        if holdout:
            stimulus = """
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b0; oh_i = 4'b1000; addr_i = 2'd3; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1100; addr_i = 2'd2; @(posedge clk);
"""
        else:
            stimulus = """
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0100; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b0; oh_i = 4'b0100; addr_i = 2'd2; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1010; addr_i = 2'd1; @(posedge clk);
"""
    elif holdout:
        stimulus = """
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0000; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0010; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b0; oh_i = 4'b1000; addr_i = 2'd3; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1100; addr_i = 2'd2; @(posedge clk);
"""
    else:
        stimulus = """
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0000; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0100; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b0; oh_i = 4'b0100; addr_i = 2'd2; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1010; addr_i = 2'd1; @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg [1:0] addr_i;
  reg en_i;
  wire err_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .oh_i(oh_i),
    .addr_i(addr_i),
    .en_i(en_i),
    .err_o(err_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    oh_i = 4'b0000;
    addr_i = 2'd0;
    en_i = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    oh_i = 4'b0000; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def regwe_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if holdout:
        stimulus = """
    en_i = 1'b1; oh_i = 4'b0000; @(posedge clk);
    en_i = 1'b0; oh_i = 4'b0010; @(posedge clk);
    en_i = 1'b0; oh_i = 4'b0010; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0001; @(posedge clk);
"""
    else:
        stimulus = """
    en_i = 1'b0; oh_i = 4'b0100; @(posedge clk);
    en_i = 1'b0; oh_i = 4'b0100; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0001; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0000; @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg en_i;
  wire err_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .oh_i(oh_i),
    .en_i(en_i),
    .err_o(err_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    oh_i = 4'b0000;
    en_i = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    oh_i = 4'b0000; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def arbiter_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if holdout:
        stimulus = """
    ready_i = 1'b1; req_i = 4'b1100; @(posedge clk);
    ready_i = 1'b0; req_i = 4'b0110; @(posedge clk);
    ready_i = 1'b1; req_i = 4'b0110; @(posedge clk);
"""
    else:
        stimulus = """
    ready_i = 1'b1; req_i = 4'b0011; @(posedge clk);
    ready_i = 1'b0; req_i = 4'b0100; @(posedge clk);
    ready_i = 1'b0; req_i = 4'b1010; @(posedge clk);
    ready_i = 1'b1; req_i = 4'b1010; @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg [3:0] req_i;
  reg ready_i;
  wire [3:0] gnt_o;
  wire [1:0] idx_o;
  wire valid_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .req_i(req_i),
    .ready_i(ready_i),
    .gnt_o(gnt_o),
    .idx_o(idx_o),
    .valid_o(valid_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    req_i = 4'b0000;
    ready_i = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    req_i = 4'b0000; ready_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def fifo_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if case_name == "case125_prim_fifo_wrap_late" and holdout:
        stimulus = """
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
"""
    elif case_name == "case125_prim_fifo_wrap_late":
        stimulus = """
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
"""
    elif case_name == "case124_prim_fifo_clear_ignored" and holdout:
        stimulus = """
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    clr_i = 1'b1; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b1; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
"""
    elif case_name == "case124_prim_fifo_clear_ignored":
        stimulus = """
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b1; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b1; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
"""
    elif holdout:
        stimulus = """
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    clr_i = 1'b1; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
"""
    else:
        stimulus = """
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b1; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b0; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
    incr_wptr_i = 1'b1; @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg clr_i;
  reg incr_wptr_i;
  reg incr_rptr_i;
  wire [1:0] wptr_o;
  wire [1:0] rptr_o;
  wire full_o;
  wire empty_o;
  wire [2:0] depth_o;
  wire err_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
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

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    clr_i = 1'b0;
    incr_wptr_i = 1'b0;
    incr_rptr_i = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; clr_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def intr_event_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if case_name == "case128_prim_intr_event_mask_stall":
        stimulus = """
    reg2hw_intr_enable_q_i = 1'b1;
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    @(posedge clk);
    sw_clear = 1'b1; @(posedge clk);
    sw_clear = 1'b0; @(posedge clk);
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    @(posedge clk);
"""
        if holdout:
            stimulus = """
    reg2hw_intr_enable_q_i = 1'b1;
    @(posedge clk);
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    sw_clear = 1'b1; @(posedge clk);
    sw_clear = 1'b0; @(posedge clk);
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    @(posedge clk);
"""
        return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg event_intr_i;
  reg reg2hw_intr_enable_q_i;
  reg reg2hw_intr_test_q_i;
  reg reg2hw_intr_test_qe_i;
  reg reg2hw_intr_state_q_i;
  reg sw_clear;
  reg pending_state_valid;
  reg pending_state_q;
  wire hw2reg_intr_state_de_o;
  wire hw2reg_intr_state_d_o;
  wire intr_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .event_intr_i(event_intr_i),
    .reg2hw_intr_enable_q_i(reg2hw_intr_enable_q_i),
    .reg2hw_intr_test_q_i(reg2hw_intr_test_q_i),
    .reg2hw_intr_test_qe_i(reg2hw_intr_test_qe_i),
    .reg2hw_intr_state_q_i(reg2hw_intr_state_q_i),
    .hw2reg_intr_state_de_o(hw2reg_intr_state_de_o),
    .hw2reg_intr_state_d_o(hw2reg_intr_state_d_o),
    .intr_o(intr_o)
  );

  always #5 clk = ~clk;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reg2hw_intr_state_q_i <= 1'b0;
      pending_state_valid <= 1'b0;
      pending_state_q <= 1'b0;
    end else if (sw_clear) begin
      reg2hw_intr_state_q_i <= 1'b0;
      pending_state_valid <= 1'b0;
    end else if (pending_state_valid) begin
      reg2hw_intr_state_q_i <= pending_state_q;
      pending_state_valid <= 1'b0;
    end else if (hw2reg_intr_state_de_o) begin
      pending_state_q <= hw2reg_intr_state_d_o;
      pending_state_valid <= 1'b1;
    end
  end

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    event_intr_i = 1'b0;
    reg2hw_intr_enable_q_i = 1'b0;
    reg2hw_intr_test_q_i = 1'b0;
    reg2hw_intr_test_qe_i = 1'b0;
    sw_clear = 1'b0;
    pending_state_valid = 1'b0;
    pending_state_q = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    event_intr_i = 1'b0; reg2hw_intr_enable_q_i = 1'b0; sw_clear = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""
    elif case_name in {"case111_prim_intr_output_or_mask", "case135_prim_intr_enable_mask_ignored"} and holdout:
        stimulus = """
    reg2hw_intr_enable_q_i = 1'b1;
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b1; @(posedge clk);
"""
    elif case_name in {"case111_prim_intr_output_or_mask", "case135_prim_intr_enable_mask_ignored"}:
        stimulus = """
    reg2hw_intr_enable_q_i = 1'b1;
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b1; @(posedge clk);
    sw_clear = 1'b1; @(posedge clk);
    sw_clear = 1'b0; @(posedge clk);
"""
    elif holdout:
        stimulus = """
    reg2hw_intr_enable_q_i = 1'b1;
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    @(posedge clk);
    sw_clear = 1'b1; @(posedge clk);
    sw_clear = 1'b0; @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b0;
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
"""
    else:
        stimulus = """
    reg2hw_intr_enable_q_i = 1'b1;
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b1; @(posedge clk);
    sw_clear = 1'b1; @(posedge clk);
    sw_clear = 1'b0; @(posedge clk);
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg event_intr_i;
  reg reg2hw_intr_enable_q_i;
  reg reg2hw_intr_test_q_i;
  reg reg2hw_intr_test_qe_i;
  reg reg2hw_intr_state_q_i;
  reg sw_clear;
  wire hw2reg_intr_state_de_o;
  wire hw2reg_intr_state_d_o;
  wire intr_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .event_intr_i(event_intr_i),
    .reg2hw_intr_enable_q_i(reg2hw_intr_enable_q_i),
    .reg2hw_intr_test_q_i(reg2hw_intr_test_q_i),
    .reg2hw_intr_test_qe_i(reg2hw_intr_test_qe_i),
    .reg2hw_intr_state_q_i(reg2hw_intr_state_q_i),
    .hw2reg_intr_state_de_o(hw2reg_intr_state_de_o),
    .hw2reg_intr_state_d_o(hw2reg_intr_state_d_o),
    .intr_o(intr_o)
  );

  always #5 clk = ~clk;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reg2hw_intr_state_q_i <= 1'b0;
    end else if (sw_clear) begin
      reg2hw_intr_state_q_i <= 1'b0;
    end else if (hw2reg_intr_state_de_o) begin
      reg2hw_intr_state_q_i <= hw2reg_intr_state_d_o;
    end
  end

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    event_intr_i = 1'b0;
    reg2hw_intr_enable_q_i = 1'b0;
    reg2hw_intr_test_q_i = 1'b0;
    reg2hw_intr_test_qe_i = 1'b0;
    sw_clear = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    event_intr_i = 1'b0; reg2hw_intr_enable_q_i = 1'b0; sw_clear = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def intr_status_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if holdout:
        stimulus = """
    reg2hw_intr_enable_q_i = 1'b1;
    @(posedge clk);
    reg2hw_intr_test_q_i = 1'b1; reg2hw_intr_test_qe_i = 1'b1; @(posedge clk);
    reg2hw_intr_test_q_i = 1'b1; reg2hw_intr_test_qe_i = 1'b1; @(posedge clk);
    reg2hw_intr_test_qe_i = 1'b0; @(posedge clk);
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
"""
    else:
        stimulus = """
    reg2hw_intr_enable_q_i = 1'b1;
    @(posedge clk);
    reg2hw_intr_test_q_i = 1'b1; reg2hw_intr_test_qe_i = 1'b1; @(posedge clk);
    reg2hw_intr_test_q_i = 1'b1; reg2hw_intr_test_qe_i = 1'b1; @(posedge clk);
    reg2hw_intr_test_qe_i = 1'b0; @(posedge clk);
    @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg event_intr_i;
  reg reg2hw_intr_enable_q_i;
  reg reg2hw_intr_test_q_i;
  reg reg2hw_intr_test_qe_i;
  reg reg2hw_intr_state_q_i;
  wire hw2reg_intr_state_de_o;
  wire hw2reg_intr_state_d_o;
  wire intr_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .event_intr_i(event_intr_i),
    .reg2hw_intr_enable_q_i(reg2hw_intr_enable_q_i),
    .reg2hw_intr_test_q_i(reg2hw_intr_test_q_i),
    .reg2hw_intr_test_qe_i(reg2hw_intr_test_qe_i),
    .reg2hw_intr_state_q_i(reg2hw_intr_state_q_i),
    .hw2reg_intr_state_de_o(hw2reg_intr_state_de_o),
    .hw2reg_intr_state_d_o(hw2reg_intr_state_d_o),
    .intr_o(intr_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    event_intr_i = 1'b0;
    reg2hw_intr_enable_q_i = 1'b0;
    reg2hw_intr_test_q_i = 1'b0;
    reg2hw_intr_test_qe_i = 1'b0;
    reg2hw_intr_state_q_i = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    reg2hw_intr_test_q_i = 1'b0; reg2hw_intr_test_qe_i = 1'b0; event_intr_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def edge_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    stimulus = """
    @(negedge clk); d_i = 1'b1;
    @(posedge clk);
    @(negedge clk); d_i = 1'b1;
    @(posedge clk);
    @(negedge clk); d_i = 1'b0;
    @(posedge clk);
    @(negedge clk); d_i = 1'b0;
    @(posedge clk);
"""
    if holdout:
        stimulus = """
    @(negedge clk); d_i = 1'b1;
    @(posedge clk);
    @(negedge clk); d_i = 1'b0;
    @(posedge clk);
    @(negedge clk); d_i = 1'b1;
    @(posedge clk);
    @(negedge clk); d_i = 1'b0;
    @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg d_i;
  wire q_sync_o;
  wire q_posedge_pulse_o;
  wire q_negedge_pulse_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .d_i(d_i),
    .q_sync_o(q_sync_o),
    .q_posedge_pulse_o(q_posedge_pulse_o),
    .q_negedge_pulse_o(q_negedge_pulse_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    d_i = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    @(posedge clk);
    $finish;
  end
endmodule
"""


def filter_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if case_name == "case116_prim_filter_late_accept" and holdout:
        stimulus = """
    enable_i = 1'b1; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b0; @(posedge clk);
    filter_i = 1'b0; @(posedge clk);
"""
    elif case_name == "case116_prim_filter_late_accept":
        stimulus = """
    enable_i = 1'b1; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b0; @(posedge clk);
    filter_i = 1'b0; @(posedge clk);
"""
    elif case_name in {"case117_prim_filter_bypass_stale", "case131_prim_filter_disabled_bypass_stale_alt"} and holdout:
        stimulus = """
    enable_i = 1'b1; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    enable_i = 1'b0; filter_i = 1'b0; @(posedge clk);
    enable_i = 1'b1; filter_i = 1'b0; @(posedge clk);
"""
    elif case_name in {"case117_prim_filter_bypass_stale", "case131_prim_filter_disabled_bypass_stale_alt"}:
        stimulus = """
    enable_i = 1'b1; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    enable_i = 1'b0; filter_i = 1'b0; @(posedge clk);
    enable_i = 1'b1; filter_i = 1'b0; @(posedge clk);
"""
    elif holdout:
        stimulus = """
    enable_i = 1'b1; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b0; @(posedge clk);
    filter_i = 1'b0; @(posedge clk);
    enable_i = 1'b0; filter_i = 1'b1; @(posedge clk);
"""
    else:
        stimulus = """
    enable_i = 1'b1; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    enable_i = 1'b0; filter_i = 1'b0; @(posedge clk);
    enable_i = 1'b1; filter_i = 1'b0; @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg enable_i;
  reg filter_i;
  wire filter_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .enable_i(enable_i),
    .filter_i(filter_i),
    .filter_o(filter_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    enable_i = 1'b0;
    filter_i = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    enable_i = 1'b0; filter_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def filter_ctr_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if case_name in {"case120_prim_filter_ctr_bypass_stale", "case136_prim_filter_ctr_disabled_bypass_stale_alt"} and holdout:
        stimulus = """
    enable_i = 1'b1; thresh_i = 2'd3; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    enable_i = 1'b0; filter_i = 1'b0; @(posedge clk);
"""
    elif case_name in {"case120_prim_filter_ctr_bypass_stale", "case136_prim_filter_ctr_disabled_bypass_stale_alt"}:
        stimulus = """
    enable_i = 1'b1; thresh_i = 2'd2; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    enable_i = 1'b0; filter_i = 1'b0; @(posedge clk);
    enable_i = 1'b1; thresh_i = 2'd2; filter_i = 1'b0; @(posedge clk);
"""
    elif holdout:
        stimulus = """
    enable_i = 1'b1; thresh_i = 2'd3; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    enable_i = 1'b0; filter_i = 1'b0; @(posedge clk);
"""
    else:
        stimulus = """
    enable_i = 1'b1; thresh_i = 2'd2; filter_i = 1'b1; @(posedge clk);
    filter_i = 1'b1; @(posedge clk);
    enable_i = 1'b0; filter_i = 1'b0; @(posedge clk);
    enable_i = 1'b1; thresh_i = 2'd2; filter_i = 1'b0; @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg enable_i;
  reg filter_i;
  reg [1:0] thresh_i;
  wire filter_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .enable_i(enable_i),
    .filter_i(filter_i),
    .thresh_i(thresh_i),
    .filter_o(filter_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    enable_i = 1'b0;
    filter_i = 1'b0;
    thresh_i = 2'd2;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    enable_i = 1'b0; filter_i = 1'b0; thresh_i = 2'd2; @(posedge clk);
    $finish;
  end
endmodule
"""


def count_tb(case_name: str, top: str, holdout: bool) -> str:
    vcd_name = f"{case_id(case_name)}{'_holdout' if holdout else ''}.vcd"
    if holdout:
        stimulus = """
    commit_i = 1'b1; set_i = 1'b1; set_cnt_i = 4'h4; @(posedge clk);
    set_i = 1'b0; @(posedge clk);
    commit_i = 1'b0; incr_en_i = 1'b1; step_i = 4'h3; @(posedge clk);
    incr_en_i = 1'b0; commit_i = 1'b1; @(posedge clk);
    incr_en_i = 1'b1; decr_en_i = 1'b1; step_i = 4'h1; @(posedge clk);
    incr_en_i = 1'b0; decr_en_i = 1'b0; @(posedge clk);
    set_i = 1'b1; set_cnt_i = 4'hf; @(posedge clk);
    set_i = 1'b0; incr_en_i = 1'b1; step_i = 4'h2; @(posedge clk);
    incr_en_i = 1'b0; @(posedge clk);
"""
    else:
        stimulus = """
    commit_i = 1'b1; set_i = 1'b1; set_cnt_i = 4'h3; @(posedge clk);
    set_i = 1'b0; @(posedge clk);
    commit_i = 1'b0; incr_en_i = 1'b1; step_i = 4'h5; @(posedge clk);
    incr_en_i = 1'b0; commit_i = 1'b1; @(posedge clk);
    incr_en_i = 1'b1; decr_en_i = 1'b1; step_i = 4'h1; @(posedge clk);
    incr_en_i = 1'b0; decr_en_i = 1'b0; @(posedge clk);
    set_i = 1'b1; set_cnt_i = 4'hf; @(posedge clk);
    set_i = 1'b0; incr_en_i = 1'b1; step_i = 4'h1; @(posedge clk);
    incr_en_i = 1'b0; @(posedge clk);
    set_i = 1'b1; set_cnt_i = 4'h6; @(posedge clk);
    set_i = 1'b0; @(posedge clk);
"""
    return f"""`timescale 1ns/1ps
module tb_{case_id(case_name)};
  reg clk;
  reg rst_n;
  reg clr_i;
  reg set_i;
  reg [3:0] set_cnt_i;
  reg incr_en_i;
  reg decr_en_i;
  reg [3:0] step_i;
  reg commit_i;
  wire [3:0] cnt_o;
  wire [3:0] cnt_after_commit_o;
  wire err_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
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

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    clr_i = 1'b0;
    set_i = 1'b0;
    set_cnt_i = 4'h0;
    incr_en_i = 1'b0;
    decr_en_i = 1'b0;
    step_i = 4'h1;
    commit_i = 1'b1;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_id(case_name)});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    clr_i = 1'b0; set_i = 1'b0; incr_en_i = 1'b0; decr_en_i = 1'b0; commit_i = 1'b1; @(posedge clk);
    $finish;
  end
endmodule
"""


def render_tb(case_entry: Dict[str, object], holdout: bool) -> str:
    case_name = str(case_entry["name"])
    top = str(case_entry["dut_top_module"])
    source_module = str(case_entry["source_module"])
    bug_family = str(case_entry.get("bug_family", ""))

    if source_module == "prim_onehot_check":
        return onehot_tb(case_name, top, holdout)
    if source_module == "prim_reg_we_check":
        return regwe_tb(case_name, top, holdout)
    if source_module == "prim_arbiter_fixed":
        return arbiter_tb(case_name, top, holdout)
    if source_module == "prim_fifo_sync_cnt":
        return fifo_tb(case_name, top, holdout)
    if source_module == "prim_intr_hw":
        if "test_pulse_capture" in bug_family:
            return intr_status_tb(case_name, top, holdout)
        return intr_event_tb(case_name, top, holdout)
    if source_module == "prim_edge_detector":
        return edge_tb(case_name, top, holdout)
    if source_module == "prim_filter":
        return filter_tb(case_name, top, holdout)
    if source_module == "prim_filter_ctr":
        return filter_ctr_tb(case_name, top, holdout)
    if source_module == "prim_count":
        return count_tb(case_name, top, holdout)
    raise ValueError(f"Unsupported source module for tb generation: {source_module}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate family-level testbench templates for the real RTL mutation dataset."
    )
    parser.add_argument("--root", required=True, help="Dataset root.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    for case_entry in load_manifest(root):
      case_dir = root / str(case_entry["name"])
      (case_dir / "tb.v").write_text(render_tb(case_entry, holdout=False), encoding="utf-8", newline="\n")
      (case_dir / "tb_holdout.v").write_text(render_tb(case_entry, holdout=True), encoding="utf-8", newline="\n")
      print(f"[OK] Wrote tb.v and tb_holdout.v for {case_entry['name']}")


if __name__ == "__main__":
    main()
