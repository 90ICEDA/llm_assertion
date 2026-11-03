`timescale 1ns/1ps
module tb;
  reg clk_i = 1'b0;
  always #5 clk_i = ~clk_i;
  reg rst_ni = 1'b0;
  reg [3:0] req_i = 4'b0000;
  reg [31:0] data_i = 32'h80604020;
  reg ready_i = 1'b0;
  wire [3:0] gnt_o;
  wire [1:0] idx_o;
  wire valid_o;
  wire [7:0] data_o;
  prim_arbiter_fixed_case dut (.*);
  initial begin
    if ($test$plusargs("VCD")) begin
      $dumpfile("wave.vcd");
      $dumpvars(0, tb);
    end
    $monitor("T=%0t rst=%b req=%b ready=%b gnt=%b idx=%0d valid=%b data=%h",
             $time, rst_ni, req_i, ready_i, gnt_o, idx_o, valid_o, data_o);
    repeat (2) @(posedge clk_i);
    @(negedge clk_i); rst_ni = 1'b1;
    @(negedge clk_i); req_i = 4'b1001; ready_i = 1'b1;
    repeat (2) @(posedge clk_i);
    @(negedge clk_i); ready_i = 1'b0;
    repeat (2) @(posedge clk_i);
    @(negedge clk_i); req_i = 4'b0000;
    repeat (2) @(posedge clk_i);
    $finish;
  end
endmodule
