`timescale 1ns/1ps
module tb;
  reg clk_src_i=0,clk_dst_i=0; always #5 clk_src_i=~clk_src_i; always #5 clk_dst_i=~clk_dst_i;
  reg rst_src_ni=0,rst_dst_ni=0,src_pulse_i=0; wire dst_pulse_o; wire q_o=dst_pulse_o;
  prim_pulse_sync dut(.*);
  initial begin
    #22 rst_src_ni=1; rst_dst_ni=1;
    #8 src_pulse_i=1; #10 src_pulse_i=0;
    #70 $finish;
  end
endmodule
