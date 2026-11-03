`timescale 1ns/1ps
module tb;
  reg clk_i = 0;
  reg rst_ni = 0;
  reg clr_i = 0;
  always #5 clk_i = ~clk_i;
  reg set_cnt_i=0,clr_cnt_i=0; wire is_zero_o; wire [3:0] count_o;
  cc_exp_backoff dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin
      $dumpfile("wave.vcd");
      $dumpvars(0,tb);
    end
    $monitor("T=%0t set=%b clear=%b zero=%b count=%d",$time,set_cnt_i,clr_cnt_i,is_zero_o,count_o);
    #12 rst_ni = 1;
    #13 set_cnt_i=1; #10 set_cnt_i=0; #10 set_cnt_i=1; #10 set_cnt_i=0; #10 set_cnt_i=1; clr_cnt_i=1; #10 set_cnt_i=0; clr_cnt_i=0;
    #40 $finish;
  end
endmodule
