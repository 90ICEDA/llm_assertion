`timescale 1ns/1ps
module tb;logic clk_i=0,rst_ni=0,clr_i=0,set_i=0,incr_en_i=0,decr_en_i=0,commit_i=1;logic[3:0]set_cnt_i=0,step_i=1,cnt_o,cnt_after_commit_o;logic err_o;
always #5 clk_i=~clk_i;prim_count dut(.*);initial begin string vcd;if(!$value$plusargs("VCD=%s",vcd))vcd="trace.vcd";$dumpfile(vcd);$dumpvars(0,tb);@(posedge clk_i);#1;rst_ni=1;set_i=1;set_cnt_i=2;@(posedge clk_i);#1;set_i=0;commit_i=0;incr_en_i=1;step_i=2;repeat(3)@(posedge clk_i);#1;commit_i=1;@(posedge clk_i);repeat(3)@(posedge clk_i);$finish;end endmodule
