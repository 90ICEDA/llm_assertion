`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i; reg rst_ni=0,ready_i=0; reg [1:0] req_i=0; wire [1:0] gnt_o; wire q_o=gnt_o[0]; cc_rr_arb_tree dut(.*);
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(0,tb);
    #22 rst_ni=1; #8 req_i=2'b01; #10 req_i=2'b10; #30 ready_i=1; #20 $finish;
  end
endmodule
