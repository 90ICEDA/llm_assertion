`timescale 1ns/1ps
module tb;
  reg clk_i = 0;
  reg rst_ni = 0;
  reg clr_i = 0;
  always #5 clk_i = ~clk_i;
  reg clr_max_i=0,en_i=0,down_i=0; reg[3:0]delta_i=1; wire[3:0]q_o,max_o;
  cc_max_counter dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin
      $dumpfile("wave.vcd");
      $dumpvars(0,tb);
    end
    $monitor("T=%0t en=%b down=%b q=%d max=%d",$time,en_i,down_i,q_o,max_o);
    #12 rst_ni = 1;
    #13 en_i=1;delta_i=4;#10 en_i=0;#20 en_i=1;delta_i=1;#10 en_i=0;
    #40 $finish;
  end
endmodule
