`timescale 1ns/1ps
module tb;
  logic clk_i = 0, rst_ni = 0, clr_i = 0;
  logic incr_wptr_i = 0, incr_rptr_i = 0;
  logic [1:0] wptr_o, rptr_o;
  logic full_o, empty_o;
  logic [2:0] depth_o;
  logic err_o;
  always #4 clk_i = ~clk_i;
  prim_fifo_sync_cnt #(.Depth(4), .Secure(0), .NeverClears(0)) dut (.*);
  task automatic pulse(input bit wr, input bit rd);
    begin
      @(negedge clk_i); incr_wptr_i = wr; incr_rptr_i = rd;
      @(negedge clk_i); incr_wptr_i = 0; incr_rptr_i = 0;
    end
  endtask
  initial begin
    string vcd;
    if (!$value$plusargs("VCD=%s", vcd)) vcd = "trace.vcd";
    $dumpfile(vcd); $dumpvars(0, tb);
    repeat (3) @(posedge clk_i); rst_ni <= 1;
    pulse(1,0); pulse(1,0); pulse(1,1); pulse(1,0);
    pulse(0,1);
    repeat (3) @(posedge clk_i);
    $finish;
  end
endmodule
