// AF_DECOY_SOURCE: case131_prim_filter_disabled_bypass_stale_alt
`timescale 1ns/1ps
module tb_case131;
  reg clk;
  reg rst_n;
  reg enable_i;
  reg filter_i;
  wire filter_o;

  dut_case131_prim_filter_disabled_bypass_stale_alt u_dut (
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

    $dumpfile("case131_decoy.vcd");
    $dumpvars(0, tb_case131);

    repeat (2) @(negedge clk);
    rst_n = 1'b1;

    
    // AF_DECOY_IDLE
    @(posedge clk);@(negedge clk); enable_i = 1'b1; filter_i = 1'b0;
    @(negedge clk); filter_i = 1'b0;
    @(negedge clk); filter_i = 1'b0;
    @(negedge clk); enable_i = 1'b0; filter_i = 1'b1;
    @(negedge clk); enable_i = 1'b0; filter_i = 1'b1;
    @(negedge clk); enable_i = 1'b1; filter_i = 1'b1;
    @(posedge clk);
    $finish;
  end
endmodule
