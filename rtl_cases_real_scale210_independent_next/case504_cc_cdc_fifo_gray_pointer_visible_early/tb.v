`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0; reg [2:0] wr_gray_i=0; wire [2:0] rd_gray_o; wire q_o=|rd_gray_o; cc_cdc_fifo_gray dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1; #8 wr_gray_i=3'b001; #40 wr_gray_i=3'b011; #50 $finish;
  end
endmodule
