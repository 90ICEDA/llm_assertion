`timescale 1ns/1ps
module tb;
  reg clk_i = 0;
  reg rst_ni = 0;
  reg clr_i = 0;
  always #5 clk_i = ~clk_i;
  reg valid_i=0; reg [7:0] data_i=0; reg [1:0] sel_i=0; reg [3:0] ready_i=0; wire ready_o; wire [3:0] valid_o; wire [7:0] data_o;
  cc_stream_demux dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin
      $dumpfile("wave.vcd");
      $dumpvars(0,tb);
    end
    $monitor("T=%0t vi=%b sel=%d ri=%b ro=%b vo=%b",$time,valid_i,sel_i,ready_i,ready_o,valid_o);
    #12 rst_ni = 1;
    #13 valid_i=1; data_i=8'h73; sel_i=1; ready_i=4'b0101; #20 valid_i=0;
    #40 $finish;
  end
endmodule
