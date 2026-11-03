`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,s_valid=0; reg [1:0] route_match=0,m_ready=0; reg [7:0] s_data=0; wire [1:0] m_valid; wire [15:0] m_data; wire q_o=m_valid[0]; axis_switch dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #12 rst_ni=1; #18 s_valid=1;route_match=3;m_ready=3;s_data=8'h6D; #30 s_valid=0; #30 $finish;
  end
endmodule
