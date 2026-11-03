`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0; reg [2:0] in_i=0; reg en_i=0; wire [7:0] out_o;
  prim_onehot_enc_case dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin $dumpfile("wave.vcd"); $dumpvars(0,tb); end
    $monitor("T=%0t rst=%b en=%b in=%0d out=%h",$time,rst_ni,en_i,in_i,out_o);
    repeat(3) @(posedge clk_i);
    @(negedge clk_i); rst_ni=1;
    @(negedge clk_i); en_i=1; in_i=3'd6;
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); en_i=0; in_i=3'd2;
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); in_i=3'd4;
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); en_i=1;
    repeat(2) @(posedge clk_i); $finish;
  end
endmodule
