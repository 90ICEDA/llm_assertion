`timescale 1ns/1ps
module tb_case127;
  reg clk;
  reg rst_n;
  reg clr_i;
  reg set_i;
  reg [3:0] set_cnt_i;
  reg incr_en_i;
  reg decr_en_i;
  reg [3:0] step_i;
  reg commit_i;
  wire [3:0] cnt_o;
  wire [3:0] cnt_after_commit_o;
  wire err_o;

  dut_case127_prim_count_set_secondary_mismatch u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .clr_i(clr_i),
    .set_i(set_i),
    .set_cnt_i(set_cnt_i),
    .incr_en_i(incr_en_i),
    .decr_en_i(decr_en_i),
    .step_i(step_i),
    .commit_i(commit_i),
    .cnt_o(cnt_o),
    .cnt_after_commit_o(cnt_after_commit_o),
    .err_o(err_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    clr_i = 1'b0;
    set_i = 1'b0;
    set_cnt_i = 4'h0;
    incr_en_i = 1'b0;
    decr_en_i = 1'b0;
    step_i = 4'h1;
    commit_i = 1'b1;

    $dumpfile("case127_holdout.vcd");
    $dumpvars(0, tb_case127);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    commit_i = 1'b1; set_i = 1'b1; set_cnt_i = 4'h4; @(posedge clk);
    set_i = 1'b0; @(posedge clk);
    commit_i = 1'b0; incr_en_i = 1'b1; step_i = 4'h3; @(posedge clk);
    incr_en_i = 1'b0; commit_i = 1'b1; @(posedge clk);
    incr_en_i = 1'b1; decr_en_i = 1'b1; step_i = 4'h1; @(posedge clk);
    incr_en_i = 1'b0; decr_en_i = 1'b0; @(posedge clk);
    set_i = 1'b1; set_cnt_i = 4'hf; @(posedge clk);
    set_i = 1'b0; incr_en_i = 1'b1; step_i = 4'h2; @(posedge clk);
    incr_en_i = 1'b0; @(posedge clk);

    clr_i = 1'b0; set_i = 1'b0; incr_en_i = 1'b0; decr_en_i = 1'b0; commit_i = 1'b1; @(posedge clk);
    $finish;
  end
endmodule
