`timescale 1ns/1ps
module tb;
  reg clk_i=0;
  always #5 clk_i=~clk_i;
  reg rst_ni=0;
  reg ack_i=0;
  reg start_i=0;
  
  wire q_o;
  wire [7:0] state_o;
  cc_isochronous_4phase_handshake dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1;
    #8 start_i=1; #10 start_i=0; #10 ack_i=1; #20 ack_i=0;
    #90 $finish;
  end
endmodule
