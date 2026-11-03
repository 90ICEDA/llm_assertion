// AF_DECOY_SOURCE: case275_fifo_v1_from_case130_prim_fifo_empty_early
`timescale 1ns/1ps
module tb_case275;
  reg clk;
  reg rst_n;
  reg clr_i;
  reg incr_wptr_i;
  reg incr_rptr_i;
  wire [1:0] wptr_o;
  wire [1:0] rptr_o;
  wire full_o;
  wire empty_o;
  wire [2:0] depth_o;
  wire err_o;

  dut_case130_prim_fifo_empty_early u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .clr_i(clr_i),
    .incr_wptr_i(incr_wptr_i),
    .incr_rptr_i(incr_rptr_i),
    .wptr_o(wptr_o),
    .rptr_o(rptr_o),
    .full_o(full_o),
    .empty_o(empty_o),
    .depth_o(depth_o),
    .err_o(err_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    clr_i = 1'b0;
    incr_wptr_i = 1'b0;
    incr_rptr_i = 1'b0;

    $dumpfile("case275_decoy.vcd");
    $dumpvars(0, tb_case275);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
    
    // AF_DECOY_IDLE
    @(posedge clk);clr_i = 1'b0; incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b0; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b0; incr_wptr_i = 1'b1; incr_rptr_i = 1'b0; @(posedge clk);
    clr_i = 1'b0; incr_wptr_i = 1'b0; incr_rptr_i = 1'b1; @(posedge clk);
    clr_i = 1'b0; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
