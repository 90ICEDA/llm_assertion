`timescale 1ns/1ps
module tb;
  reg clk_i = 0;
  reg rst_ni = 0;
  reg clr_i = 0;
  always #5 clk_i = ~clk_i;
  reg valid_i=0,drop_i=0,ready_i=0; wire ready_o,valid_o;
  cc_stream_filter dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin
      $dumpfile("wave.vcd");
      $dumpvars(0,tb);
    end
    $monitor("T=%0t vi=%b drop=%b ri=%b ro=%b vo=%b",$time,valid_i,drop_i,ready_i,ready_o,valid_o);
    #12 rst_ni = 1;
    #13 valid_i=1; drop_i=0; ready_i=0; #10 drop_i=1; #20 valid_i=0;
    #40 $finish;
  end
endmodule
