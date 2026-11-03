`timescale 1ns/1ps
module tb;
  reg clk_i = 0;
  reg rst_ni = 0;
  reg clr_i = 0;
  always #5 clk_i = ~clk_i;
  reg [7:0] addr_i=0; reg en_i=0; wire [1:0] sel_o; wire valid_o,error_o;
  cc_addr_decode_overlap dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin
      $dumpfile("wave.vcd");
      $dumpvars(0,tb);
    end
    $monitor("T=%0t addr=%h en=%b sel=%b valid=%b err=%b",$time,addr_i,en_i,sel_o,valid_o,error_o);
    #12 rst_ni = 1;
    #13 en_i=1; addr_i=8'h25; #10 addr_i=8'h3f; #20 en_i=0;
    #40 $finish;
  end
endmodule
