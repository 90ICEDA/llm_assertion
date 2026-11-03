`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0; reg [3:0] error_valid_i=0,error_overflow_i=0;
  reg [31:0] error_payload_i=32'hd4c3b2a1;
  wire error_valid_o,error_overflow_o; wire [7:0] error_payload_o; wire q_o=error_overflow_o;
  prim_racl_error_arb dut(.*);
  initial begin
    #23 rst_ni=1;
    #7 error_valid_i=4'b1100;
    #30 error_valid_i=4'b0001;
    #10 error_valid_i=4'b0011;
    #20 error_valid_i=0;
    #30 $finish;
  end
endmodule
