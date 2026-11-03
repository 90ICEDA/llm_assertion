`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,req_i=0; wire ack_o; wire q_o=ack_o; cc_cdc_2phase dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1; #8 req_i=1; #30 req_i=0; #50 $finish;
  end
endmodule
