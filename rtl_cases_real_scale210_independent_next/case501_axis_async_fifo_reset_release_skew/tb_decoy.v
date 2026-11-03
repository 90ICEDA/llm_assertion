`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,s_axis_tvalid=0; reg [7:0] s_axis_tdata=0; wire s_axis_tready,m_axis_tvalid; wire [7:0] m_axis_tdata; wire q_o=m_axis_tvalid; axis_async_fifo dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #27 rst_ni=1; #3 s_axis_tdata=8'h5C; s_axis_tvalid=1; #20 s_axis_tvalid=0; #50 $finish;
  end
endmodule
