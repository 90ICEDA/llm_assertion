// AF_TEMPORAL_VARIANT_SOURCE: case=case122_prim_filter_ctr_streak_reset_ignored, track=holdout, role=primary
`timescale 1ns/1ps
module tb_case322;
  reg clk;
  reg rst_n;
  reg enable_i;
  reg filter_i;
  reg [1:0] thresh_i;
  wire filter_o;
  wire second_new_sample_dbg;

  dut_case122_prim_filter_ctr_streak_reset_ignored u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .enable_i(enable_i),
    .filter_i(filter_i),
    .thresh_i(thresh_i),
    .filter_o(filter_o),
    .second_new_sample_dbg(second_new_sample_dbg)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    enable_i = 1'b0;
    filter_i = 1'b0;
    thresh_i = 2'd2;

    $dumpfile("case322.vcd");
    $dumpvars(0, tb_case322);

    repeat (2) @(negedge clk);
    rst_n = 1'b1;

    @(negedge clk); enable_i = 1'b1; thresh_i = 2'd2; filter_i = 1'b1;
    @(negedge clk); filter_i = 1'b1;
    @(negedge clk); filter_i = 1'b1;
    @(negedge clk); filter_i = 1'b0;
    @(negedge clk); filter_i = 1'b0;
    @(negedge clk); filter_i = 1'b1;
    @(negedge clk); filter_i = 1'b0;
    @(negedge clk); filter_i = 1'b0;
    @(posedge clk);
    @(negedge clk); enable_i = 1'b0; filter_i = 1'b0;
    @(posedge clk);
    $finish;
  end
endmodule
