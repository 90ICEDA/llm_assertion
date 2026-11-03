`timescale 1ns/1ps
module tb; reg clk_i=0,rst_ni=0,clr_i=0;always #5 clk_i=~clk_i;reg wvalid_i=0,advance_i=0;reg[7:0]wdata_i=0;reg[2:0]step_i=1;wire wready_o,empty_o,full_o;wire[2:0]wptr_o,rptr_o;
cc_ring_buffer dut(.*);
initial begin if($test$plusargs("VCD"))begin $dumpfile("wave.vcd");$dumpvars(0,tb);end $monitor("T=%0t wp=%0d rp=%0d wv=%b adv=%b",$time,wptr_o,rptr_o,wvalid_i,advance_i);#12 rst_ni=1;#13 wvalid_i=1;wdata_i=1;#30 wvalid_i=0;advance_i=1;step_i=2;#10 wvalid_i=1;advance_i=1;wdata_i=9;#10 wvalid_i=0;advance_i=0;#40 $finish;end endmodule
