`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,s0_valid=0,s1_valid=0,m_ready=0; reg [7:0] s0_data=0,s1_data=0; wire m_valid,s0_ready,s1_ready; wire [7:0] m_data; wire q_o=(m_data==s0_data); axis_crosspoint dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #12 rst_ni=1; #18 s0_data=8'h77;s1_data=8'h88;s0_valid=1;s1_valid=1;m_ready=1; #30 s0_valid=0;s1_valid=0; #30 $finish;
  end
endmodule
