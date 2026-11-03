`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0; reg [3:0] oh_i=0; reg en_i=0; wire err_o;
  prim_reg_we_check_case dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin $dumpfile("wave.vcd"); $dumpvars(0,tb); end
    $monitor("T=%0t rst=%b en=%b oh=%b err=%b",$time,rst_ni,en_i,oh_i,err_o);
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); rst_ni=1; en_i=1; oh_i=4'b0100;
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); en_i=0; oh_i=4'b1000;
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); en_i=1; oh_i=4'b1100;
    repeat(2) @(posedge clk_i); $finish;
  end
endmodule
