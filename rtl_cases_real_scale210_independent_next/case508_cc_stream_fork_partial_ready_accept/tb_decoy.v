`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,valid_i=0; reg [1:0] ready_i=0; wire [1:0] valid_o; wire ready_o; wire q_o=ready_o; cc_stream_fork dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #12 rst_ni=1; #18 valid_i=1;ready_i=2'b01; #10 ready_i=0; #20 ready_i=3; #30 $finish;
  end
endmodule
