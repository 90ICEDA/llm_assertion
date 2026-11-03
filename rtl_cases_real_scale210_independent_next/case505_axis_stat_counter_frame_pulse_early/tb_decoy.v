`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,frame_done_i=0; reg [7:0] frame_len_i=0; wire stat_valid_o; wire [7:0] stat_len_o; wire q_o=stat_valid_o; axis_stat_counter dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #12 rst_ni=1; #18 frame_len_i=8'd5; frame_done_i=1; #10 frame_done_i=0; #60 $finish;
  end
endmodule
