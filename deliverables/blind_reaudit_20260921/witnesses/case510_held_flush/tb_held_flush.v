`timescale 1ns/1ps
module tb;
  reg clk_i=0;
  always #5 clk_i=~clk_i;
  reg rst_ni=0, flush_i=0, push_i=0;
  reg [7:0] data_i=0;
  wire valid_o;
  wire [7:0] data_o;
  cc_spill_register_flushable dut(.*);
  integer cycles=0;
  reg prior_flush=0;
  integer slot06_fail=0, slot07_fail=0;
  always @(posedge clk_i) begin
    cycles=cycles+1;
    if(rst_ni && prior_flush) begin
      if(valid_o !== 1'b0) slot06_fail=slot06_fail+1;
      if(data_o !== {7'b0,flush_i}) slot07_fail=slot07_fail+1;
      $display("WITNESS cycle=%0d prior_flush=%b flush_now=%b valid=%b data=%02h slot06_fail=%0d slot07_fail=%0d",cycles,prior_flush,flush_i,valid_o,data_o,slot06_fail,slot07_fail);
    end
    prior_flush=flush_i;
  end
  initial begin
    #12 rst_ni=1;
    #8 flush_i=1;push_i=1;data_i=8'h55;
    #10 push_i=0; // flush remains asserted for the next sampled cycle
    #10 flush_i=0;
    #20 $display("SUMMARY slot06_fail=%0d slot07_fail=%0d",slot06_fail,slot07_fail);
    $finish;
  end
endmodule
