`timescale 1ns/1ps
module tb;logic clk_i=0,rst_ni=0,set_crc_i=0,data_valid_i=0;logic[31:0]data_i=0,crc_in_i=0,crc_out_o;always #5 clk_i=~clk_i;
prim_crc32 dut(.*);initial begin string vcd;if(!$value$plusargs("VCD=%s",vcd))vcd="trace.vcd";$dumpfile(vcd);$dumpvars(0,tb);@(posedge clk_i);#1;rst_ni=1;set_crc_i=1;crc_in_i=32'hA5A55A5A;@(posedge clk_i);#1;set_crc_i=0;data_valid_i=1;data_i=32'hDEADBEEF;@(posedge clk_i);#1;data_valid_i=0;repeat(3)@(posedge clk_i);$finish;end endmodule
