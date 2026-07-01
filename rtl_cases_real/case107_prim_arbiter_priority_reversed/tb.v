`timescale 1ns/1ps
module tb_case107;
  reg clk;
  reg rst_n;
  reg [3:0] req_i;
  reg ready_i;
  wire [3:0] gnt_o;
  wire [1:0] idx_o;
  wire valid_o;

  dut_case107_prim_arbiter_priority_reversed u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .req_i(req_i),
    .ready_i(ready_i),
    .gnt_o(gnt_o),
    .idx_o(idx_o),
    .valid_o(valid_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    req_i = 4'b0000;
    ready_i = 1'b0;

    $dumpfile("case107.vcd");
    $dumpvars(0, tb_case107);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    ready_i = 1'b1; req_i = 4'b0011; @(posedge clk);
    ready_i = 1'b0; req_i = 4'b0100; @(posedge clk);
    ready_i = 1'b0; req_i = 4'b1010; @(posedge clk);
    ready_i = 1'b1; req_i = 4'b1010; @(posedge clk);

    req_i = 4'b0000; ready_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
