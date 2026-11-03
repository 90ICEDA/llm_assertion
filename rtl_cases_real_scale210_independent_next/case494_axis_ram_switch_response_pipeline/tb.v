`timescale 1ns/1ps
module tb;
  reg clk_i=0;
  always #5 clk_i=~clk_i;
  reg rst_ni=0;
  reg grant_i=0;
  reg output_ready_i=0;
  
  wire q_o;
  wire [7:0] state_o;
  axis_ram_switch dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1;
    #8 grant_i=1; output_ready_i=1; #10 grant_i=0; #10 output_ready_i=0;
    #90 $finish;
  end
endmodule
