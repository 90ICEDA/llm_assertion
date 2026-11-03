`timescale 1ns/1ps
module tb; reg clk_i=0,rst_ni=0,clr_i=0;always #5 clk_i=~clk_i;reg valid_i=0,ready_i=0;reg[7:0]data_i=0;wire ready_o,valid_o;wire[7:0]data_o;
cc_spill_register dut(.*);
initial begin if($test$plusargs("VCD"))begin $dumpfile("wave.vcd");$dumpvars(0,tb);end $monitor("T=%0t vi=%b ri=%b vo=%b do=%h",$time,valid_i,ready_i,valid_o,data_o);#12 rst_ni=1;#13 valid_i=1;data_i=8'h31;#10 valid_i=0;ready_i=1;#20 ready_i=0;#40 $finish;end endmodule
