`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0; reg [3:0] error_valid_i=0,error_overflow_i=0;
  reg [31:0] error_payload_i=32'h44332211;
  wire error_valid_o,error_overflow_o; wire [7:0] error_payload_o; wire q_o=error_overflow_o;
  prim_racl_error_arb dut(.*);
  initial begin
    #22 rst_ni=1;
    #8 error_valid_i=4'b0101;
    #20 error_valid_i=0;
    #20 error_valid_i=4'b1010;
    #20 error_valid_i=0;
    #20 $finish;
  end
endmodule
