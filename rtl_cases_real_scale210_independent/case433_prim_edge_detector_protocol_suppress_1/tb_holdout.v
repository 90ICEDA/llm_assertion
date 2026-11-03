`timescale 1ns/1ps
module tb;
  logic clk_i=0,rst_ni=0,d_i=0; logic q_sync_o,q_posedge_pulse_o,q_negedge_pulse_o;
  always #5 clk_i=~clk_i;
  prim_edge_detector #(.Width(1),.ResetValue(0),.EnSync(0)) dut (.*);
  initial begin string vcd; if (!$value$plusargs("VCD=%s",vcd)) vcd="trace.vcd";
    $dumpfile(vcd); $dumpvars(0,tb); repeat (2) @(posedge clk_i); rst_ni<=1;
    repeat (2) @(posedge clk_i); @(negedge clk_i); d_i<=1;
    repeat (2) @(posedge clk_i); @(negedge clk_i); d_i<=0;
    repeat (3) @(posedge clk_i); $finish;
  end
endmodule
