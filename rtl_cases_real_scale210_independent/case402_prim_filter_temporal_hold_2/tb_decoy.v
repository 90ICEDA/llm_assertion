`timescale 1ns/1ps
module tb;
  logic clk_i=0, rst_ni=0, enable_i=0, filter_i=0;
  logic filter_o;
  wire [3:0] stored_vector_q = dut.stored_vector_q;
  wire stored_value_q = dut.stored_value_q;
  always #5 clk_i=~clk_i;
  prim_filter #(.AsyncOn(0), .Cycles(4)) dut (.*);
  initial begin string vcd; if (!$value$plusargs("VCD=%s",vcd)) vcd="trace.vcd";
    $dumpfile(vcd); $dumpvars(0,tb);
    repeat (3) @(posedge clk_i); rst_ni<=1;
    @(negedge clk_i); enable_i<=1; filter_i<=1;
    repeat (5) @(posedge clk_i);
    @(negedge clk_i); filter_i<=0;
    repeat (7) @(posedge clk_i); $finish;
  end
endmodule
