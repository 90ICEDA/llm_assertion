`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,flush_i=0,push_i=0; reg [7:0] data_i=0; wire valid_o; wire [7:0] data_o; wire q_o=valid_o; cc_spill_register_flushable dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1; #8 flush_i=1;push_i=1;data_i=8'h55; #10 flush_i=0;push_i=0; #50 $finish;
  end
endmodule
