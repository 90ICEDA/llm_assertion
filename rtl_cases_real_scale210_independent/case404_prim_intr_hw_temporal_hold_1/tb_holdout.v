`timescale 1ns/1ps
module tb;
  logic clk_i=0, rst_ni=0; logic event_intr_i=0;
  logic reg2hw_intr_enable_q_i=1, reg2hw_intr_test_q_i=0;
  logic reg2hw_intr_test_qe_i=0, reg2hw_intr_state_q_i=0;
  logic hw2reg_intr_state_de_o, hw2reg_intr_state_d_o, intr_o;
  always #5 clk_i=~clk_i;
  prim_intr_hw #(.Width(1),.FlopOutput(1),.IntrT("Status")) dut (.*);
  initial begin string vcd; if (!$value$plusargs("VCD=%s",vcd)) vcd="trace.vcd";
    $dumpfile(vcd); $dumpvars(0,tb);
    repeat (2) @(posedge clk_i); rst_ni<=1;
    repeat (2) @(posedge clk_i); @(negedge clk_i); event_intr_i<=1;
    repeat (3) @(posedge clk_i); @(negedge clk_i); event_intr_i<=0;
    repeat (3) @(posedge clk_i); $finish;
  end
endmodule
