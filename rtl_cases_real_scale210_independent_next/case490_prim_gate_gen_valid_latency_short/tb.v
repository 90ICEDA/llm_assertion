`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0; reg valid_i=0; reg [7:0] data_i=0;
  wire valid_o; wire [7:0] data_o;
  prim_gate_gen_case dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin $dumpfile("wave.vcd"); $dumpvars(0,tb); end
    $monitor("T=%0t rst=%b vi=%b di=%h vo=%b do=%h",$time,rst_ni,valid_i,data_i,valid_o,data_o);
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); rst_ni=1;
    @(negedge clk_i); valid_i=1; data_i=8'h3c;
    @(negedge clk_i); valid_i=0; data_i=0;
    repeat(6) @(posedge clk_i);
    $finish;
  end
endmodule
