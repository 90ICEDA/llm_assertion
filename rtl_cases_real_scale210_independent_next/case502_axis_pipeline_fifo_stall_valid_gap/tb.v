`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,s_axis_tvalid=0,m_axis_tready=0; reg [7:0] s_axis_tdata=0; wire s_axis_tready,m_axis_tvalid; wire [7:0] m_axis_tdata; wire q_o=m_axis_tvalid; axis_pipeline_fifo dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1; #8 s_axis_tvalid=1; s_axis_tdata=8'h44; #10 s_axis_tvalid=0; #30 m_axis_tready=1; #30 $finish;
  end
endmodule
