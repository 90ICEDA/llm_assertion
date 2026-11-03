`timescale 1ns/1ps
module tb;
  reg clk_src_i=0; always #5 clk_src_i=~clk_src_i;
  wire clk_dst_i=clk_src_i;
  reg rst_src_ni=0,rst_dst_ni=0,req_chk_i=1,src_req_i=0,dst_ack_i=0;
  wire src_ack_o,dst_req_o; wire q_o=src_ack_o;
  prim_sync_reqack dut(.*);
  initial begin
    #23 rst_src_ni=1; rst_dst_ni=1;
    #7 src_req_i=1;
    #30 dst_ack_i=1;
    #2 src_req_i=0;
    #28 dst_ack_i=0;
    #30 $finish;
  end
endmodule
