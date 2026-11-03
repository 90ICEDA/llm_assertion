`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0,test_en_i=0,async_en_i=0; wire en_o,clk_o; wire q_o=en_o;
  prim_clock_gating_sync dut(.*);
  initial begin
    #23 rst_ni=1;
    #7 test_en_i=1; #10 test_en_i=0;
    #10 async_en_i=1;
    #60 async_en_i=0;
    #30 $finish;
  end
endmodule
