`timescale 1ns/1ps
module tb;
  logic clk_i=0, rst_ni=0; logic [3:0] oh_i=0; logic [1:0] addr_i=2'd2; logic en_i=1; logic err_o;
  prim_onehot_check #(.OneHotWidth(4),.AddrWidth(2),.AddrCheck(1),.EnableCheck(1)) dut (.clk_i(clk_i),.rst_ni(rst_ni),.oh_i(oh_i),.addr_i(addr_i),.en_i(en_i),.err_o(err_o));
  initial begin string vcd; if (!$value$plusargs("VCD=%s",vcd)) vcd="trace.vcd";
    $dumpfile(vcd); $dumpvars(0,tb); rst_ni=1; #1;
    oh_i=4'b0001 << 2; #3; oh_i=4'b0011 << 2; #3;
    oh_i=4'b0000; #2; oh_i=4'b0101; #3; $finish;
  end
endmodule
