// AF_TEMPORAL_VARIANT_SOURCE: case=case117_prim_filter_bypass_stale, track=primary, role=decoy
`timescale 1ns/1ps
module tb_case315;
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

    $dumpfile("case315_decoy.vcd");
    $dumpvars(0, tb_case315);

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
