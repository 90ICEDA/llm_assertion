`timescale 1ns/1ps
module tb;
  reg clk_i=0;
  always #5 clk_i=~clk_i;
  reg rst_ni=0;
  reg write_toggle_i=0;
  reg sample_enable_i=0;
  
  wire q_o;
  wire [7:0] state_o;
  axis_async_fifo dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1;
    #28 write_toggle_i=1; sample_enable_i=1; #10 write_toggle_i=0; #10 sample_enable_i=0;
    #90 $finish;
  end
endmodule
