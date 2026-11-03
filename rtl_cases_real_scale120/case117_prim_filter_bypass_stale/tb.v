`timescale 1ns/1ps
module tb_case117;
  reg clk;
  reg rst_n;
  reg enable_i;
  reg filter_i;
  wire filter_o;

  dut_case117_prim_filter_bypass_stale u_dut (
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

    $dumpfile("case117.vcd");
    $dumpvars(0, tb_case117);

    repeat (2) @(negedge clk);
    rst_n = 1'b1;

    @(negedge clk); enable_i = 1'b1; filter_i = 1'b1;
    @(negedge clk); filter_i = 1'b1;
    @(negedge clk); filter_i = 1'b1;
    @(negedge clk); enable_i = 1'b0; filter_i = 1'b0;
    @(negedge clk); enable_i = 1'b0; filter_i = 1'b0;
    @(negedge clk); enable_i = 1'b1; filter_i = 1'b0;
    @(posedge clk);
    $finish;
  end
endmodule
