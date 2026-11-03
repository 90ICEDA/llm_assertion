`timescale 1ns/1ps
module tb;
  logic clk_i=0, rst_ni=0, clr_i=0, incr_wptr_i=0, incr_rptr_i=0;
  logic [1:0] wptr_o,rptr_o; logic full_o,empty_o; logic [2:0] depth_o; logic err_o;
  always #5 clk_i=~clk_i;
  prim_fifo_sync_cnt #(.Depth(4),.Secure(0),.NeverClears(0)) dut (.*);
  task automatic wr; begin @(negedge clk_i); incr_wptr_i=1; @(negedge clk_i); incr_wptr_i=0; end endtask
  initial begin string vcd; if (!$value$plusargs("VCD=%s",vcd)) vcd="trace.vcd";
    $dumpfile(vcd); $dumpvars(0,tb);
    repeat (1) @(posedge clk_i); rst_ni<=1;
    repeat (5) wr();
    @(negedge clk_i); clr_i<=1; @(negedge clk_i); clr_i<=0;
    repeat (2) wr(); repeat (3) @(posedge clk_i); $finish;
  end
endmodule
