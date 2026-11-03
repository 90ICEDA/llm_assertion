`timescale 1ns/1ps
module tb_case115;
  reg clk;
  reg rst_n;
  reg d_i;
  wire q_sync_o;
  wire q_posedge_pulse_o;
  wire q_negedge_pulse_o;

  dut_case115_prim_edge_both_edges_collapsed u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .d_i(d_i),
    .q_sync_o(q_sync_o),
    .q_posedge_pulse_o(q_posedge_pulse_o),
    .q_negedge_pulse_o(q_negedge_pulse_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    d_i = 1'b0;

    $dumpfile("case115_holdout.vcd");
    $dumpvars(0, tb_case115);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    @(posedge clk); #1 d_i = 1'b1;
    @(posedge clk);
    @(posedge clk);
    @(posedge clk); #1 d_i = 1'b0;
    @(posedge clk);
    @(posedge clk);
    $finish;
  end
endmodule
