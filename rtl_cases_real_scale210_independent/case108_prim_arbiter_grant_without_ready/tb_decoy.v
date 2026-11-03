// AF_DECOY_SOURCE: case108_prim_arbiter_grant_without_ready
`timescale 1ns/1ps
module tb_case108;
  reg clk;
  reg rst_n;
  reg [3:0] req_i;
  reg ready_i;
  wire [3:0] gnt_o;
  wire [1:0] idx_o;
  wire valid_o;

  dut_case108_prim_arbiter_grant_without_ready u_dut (
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

    $dumpfile("case108_decoy.vcd");
    $dumpvars(0, tb_case108);

    repeat (2) @(posedge clk);
    @(negedge clk);
    rst_n = 1'b1;
    
    // AF_DECOY_IDLE
    @(posedge clk);@(negedge clk); ready_i = 1'b1; req_i = 4'b1100; @(posedge clk);
    @(negedge clk); ready_i = 1'b0; req_i = 4'b0110; @(posedge clk);
    @(negedge clk); ready_i = 1'b1; req_i = 4'b0110; @(posedge clk);
    @(negedge clk); req_i = 4'b0000; ready_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
