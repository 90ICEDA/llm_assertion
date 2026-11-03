#!/usr/bin/env python3
"""Materialize the missing OpenTitan harnesses for scale210 cases.

This intentionally excludes sealed pristine cases 408 and 435.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "rtl_cases_real_scale210_independent"

TARGETS = {
    401: "filter", 402: "filter", 403: "filter",
    404: "intr", 405: "intr",
    406: "fifo", 407: "fifo", 409: "fifo",
    431: "onehot", 432: "onehot",
    433: "edge", 434: "edge",
    436: "filter_ctr",
}


def common(body: str) -> str:
    return "`timescale 1ns/1ps\nmodule tb;\n" + body + "\nendmodule\n"


def make(kind: str, variant: int) -> str:
    pre = 1 + variant
    if kind == "filter":
        body = f"""  logic clk_i=0, rst_ni=0, enable_i=0, filter_i=0;
  logic filter_o;
  wire [3:0] stored_vector_q = dut.stored_vector_q;
  wire stored_value_q = dut.stored_value_q;
  always #5 clk_i=~clk_i;
  prim_filter #(.AsyncOn(0), .Cycles(4)) dut (.*);
  initial begin string vcd; if (!$value$plusargs(\"VCD=%s\",vcd)) vcd=\"trace.vcd\";
    $dumpfile(vcd); $dumpvars(0,tb);
    repeat ({pre}) @(posedge clk_i); rst_ni<=1;
    @(negedge clk_i); enable_i<=1; filter_i<=1;
    repeat (5) @(posedge clk_i);
    @(negedge clk_i); filter_i<=0;
    repeat ({5+variant}) @(posedge clk_i); $finish;
  end"""
    elif kind == "intr":
        body = f"""  logic clk_i=0, rst_ni=0; logic event_intr_i=0;
  logic reg2hw_intr_enable_q_i=1, reg2hw_intr_test_q_i=0;
  logic reg2hw_intr_test_qe_i=0, reg2hw_intr_state_q_i=0;
  logic hw2reg_intr_state_de_o, hw2reg_intr_state_d_o, intr_o;
  always #5 clk_i=~clk_i;
  prim_intr_hw #(.Width(1),.FlopOutput(1),.IntrT(\"Status\")) dut (.*);
  initial begin string vcd; if (!$value$plusargs(\"VCD=%s\",vcd)) vcd=\"trace.vcd\";
    $dumpfile(vcd); $dumpvars(0,tb);
    repeat ({pre}) @(posedge clk_i); rst_ni<=1;
    repeat ({variant+1}) @(posedge clk_i); @(negedge clk_i); event_intr_i<=1;
    repeat (3) @(posedge clk_i); @(negedge clk_i); event_intr_i<=0;
    repeat (3) @(posedge clk_i); $finish;
  end"""
    elif kind == "fifo":
        n = 5 + variant
        body = f"""  logic clk_i=0, rst_ni=0, clr_i=0, incr_wptr_i=0, incr_rptr_i=0;
  logic [1:0] wptr_o,rptr_o; logic full_o,empty_o; logic [2:0] depth_o; logic err_o;
  always #5 clk_i=~clk_i;
  prim_fifo_sync_cnt #(.Depth(4),.Secure(0),.NeverClears(0)) dut (.*);
  task automatic wr; begin @(negedge clk_i); incr_wptr_i=1; @(negedge clk_i); incr_wptr_i=0; end endtask
  initial begin string vcd; if (!$value$plusargs(\"VCD=%s\",vcd)) vcd=\"trace.vcd\";
    $dumpfile(vcd); $dumpvars(0,tb);
    repeat ({pre}) @(posedge clk_i); rst_ni<=1;
    repeat ({n}) wr();
    @(negedge clk_i); clr_i<=1; @(negedge clk_i); clr_i<=0;
    repeat (2) wr(); repeat (3) @(posedge clk_i); $finish;
  end"""
    elif kind == "onehot":
        body = f"""  logic clk_i=0, rst_ni=0; logic [3:0] oh_i=0; logic err_o;
  prim_onehot_check #(.OneHotWidth(4),.AddrWidth(2),.EnableAddrCheck(0)) dut
    (.clk_i(clk_i),.rst_ni(rst_ni),.oh_i(oh_i),.addr_i('0),.en_i(1'b1),.err_o(err_o));
  initial begin string vcd; if (!$value$plusargs(\"VCD=%s\",vcd)) vcd=\"trace.vcd\";
    $dumpfile(vcd); $dumpvars(0,tb); #1;
    oh_i=4'b0001 << {variant}; #3; oh_i=4'b0011 << {variant}; #3;
    oh_i=4'b0000; #2; oh_i=4'b0101; #3; $finish;
  end"""
    elif kind == "edge":
        body = f"""  logic clk_i=0,rst_ni=0,d_i=0; logic q_sync_o,q_posedge_pulse_o,q_negedge_pulse_o;
  always #5 clk_i=~clk_i;
  prim_edge_detector #(.Width(1),.ResetValue(0),.EnSync(0)) dut (.*);
  initial begin string vcd; if (!$value$plusargs(\"VCD=%s\",vcd)) vcd=\"trace.vcd\";
    $dumpfile(vcd); $dumpvars(0,tb); repeat ({pre}) @(posedge clk_i); rst_ni<=1;
    repeat ({variant+1}) @(posedge clk_i); @(negedge clk_i); d_i<=1;
    repeat (2) @(posedge clk_i); @(negedge clk_i); d_i<=0;
    repeat (3) @(posedge clk_i); $finish;
  end"""
    elif kind == "filter_ctr":
        body = f"""  logic clk_i=0,rst_ni=0,enable_i=0,filter_i=0; logic [1:0] thresh_i=2; logic filter_o;
  always #5 clk_i=~clk_i;
  prim_filter_ctr #(.AsyncOn(0),.CntWidth(2)) dut (.*);
  initial begin string vcd; if (!$value$plusargs(\"VCD=%s\",vcd)) vcd=\"trace.vcd\";
    $dumpfile(vcd); $dumpvars(0,tb); repeat ({pre}) @(posedge clk_i); rst_ni<=1;
    @(negedge clk_i); enable_i<=1; filter_i<=1; repeat ({4+variant}) @(posedge clk_i);
    @(negedge clk_i); filter_i<=0; repeat ({4+variant}) @(posedge clk_i); $finish;
  end"""
    else:
        raise ValueError(kind)
    return common(body)


def main() -> None:
    made = []
    for case_id, kind in TARGETS.items():
        dirs = list(ROOT.glob(f"case{case_id}_*"))
        if len(dirs) != 1:
            raise RuntimeError(f"case{case_id}: expected one directory, got {dirs}")
        case_dir = dirs[0]
        for name, variant in (("tb.v", 0), ("tb_holdout.v", 1), ("tb_decoy.v", 2)):
            path = case_dir / name
            if path.exists():
                raise RuntimeError(f"refusing to overwrite existing {path}")
            path.write_text(make(kind, variant), encoding="utf-8", newline="\n")
            made.append(path.relative_to(ROOT.parent).as_posix())
    print(f"materialized {len(made)} harnesses for {len(TARGETS)} OpenTitan cases")
    for case_id in TARGETS:
        print(f"case{case_id}")


if __name__ == "__main__":
    main()
