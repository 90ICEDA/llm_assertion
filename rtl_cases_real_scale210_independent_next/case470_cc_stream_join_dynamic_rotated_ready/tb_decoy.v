`timescale 1ns/1ps
module tb; reg clk_i=0,rst_ni=0,clr_i=0;always #5 clk_i=~clk_i;reg[3:0]inp_valid_i=0,sel_i=0;reg oup_ready_i=0;wire[3:0]inp_ready_o;wire oup_valid_o;
cc_stream_join_dynamic dut(.*);
initial begin if($test$plusargs("VCD"))begin $dumpfile("wave.vcd");$dumpvars(0,tb);end $monitor("T=%0t iv=%b sel=%b ov=%b ir=%b",$time,inp_valid_i,sel_i,oup_valid_o,inp_ready_o);#12 rst_ni=1;#8 sel_i=4'b0011;inp_valid_i=4'b1011;oup_ready_i=1;#10 sel_i=4'b1100;inp_valid_i=4'b1101;#20 oup_ready_i=0;#40 $finish;end endmodule
