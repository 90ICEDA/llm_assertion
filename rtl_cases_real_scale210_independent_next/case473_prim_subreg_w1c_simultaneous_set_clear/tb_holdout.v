`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0,we=0,de=0; reg [7:0] wd=0,d=0;
  wire qe; wire [7:0] q,ds,qs; wire [7:0] q_o=q;
  prim_subreg #(.DW(8),.RESVAL(8'h3c)) dut(.*);
  initial begin
    #23 rst_ni=1;
    #7 we=1; de=1; wd=8'h30; d=8'hf3;
    #10 we=0; de=0;
    #20 de=1; d=8'haa; #10 de=0;
    #20 we=1; de=1; wd=8'h88; d=8'hcc;
    #10 we=0; de=0;
    #30 $finish;
  end
endmodule
