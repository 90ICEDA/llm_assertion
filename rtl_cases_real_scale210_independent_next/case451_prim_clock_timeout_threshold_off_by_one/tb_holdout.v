`timescale 1ns/1ps
module tb; logic clk_i=0,clk_chk_i=0,rst_ni=0,rst_chk_ni=0,en_i=1,run_chk=1; logic timeout_o;
 always #5 clk_i=~clk_i; always begin #3; if(run_chk) clk_chk_i=~clk_chk_i; end
 prim_clock_timeout #(.TimeOutCnt(4),.CntWidth(3)) dut(.*);
 wire ack = dut.ack; wire [2:0] cnt = dut.cnt;
 initial begin string vcd;if(!$value$plusargs("VCD=%s",vcd))vcd="trace.vcd";$dumpfile(vcd);$dumpvars(0,tb);
 @(posedge clk_i);#1;rst_ni=1;rst_chk_ni=1; repeat(3) @(posedge clk_i); run_chk=0; repeat(10) @(posedge clk_i); $finish;end endmodule
