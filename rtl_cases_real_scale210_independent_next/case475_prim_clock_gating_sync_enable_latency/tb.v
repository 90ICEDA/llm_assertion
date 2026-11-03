`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0,test_en_i=0,async_en_i=0; wire en_o,clk_o; wire q_o=en_o;
  prim_clock_gating_sync dut(.*);
  initial begin
    #22 rst_ni=1;
    #8 async_en_i=1;
    #50 async_en_i=0;
    #40 $finish;
  end
endmodule
