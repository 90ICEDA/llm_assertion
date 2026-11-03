`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0,we=0,de=0; reg [7:0] wd=0,d=0;
  wire qe; wire [7:0] q,ds,qs; wire [7:0] q_o=q;
  prim_subreg #(.DW(8),.RESVAL(8'h00)) dut(.*);
  initial begin
    #22 rst_ni=1;
    #8 de=1; d=8'hf0; #10 de=0;
    #10 we=1; de=1; wd=8'h0f; d=8'hff;
    #10 we=0; de=0; wd=0; d=0;
    #30 $finish;
  end
endmodule
