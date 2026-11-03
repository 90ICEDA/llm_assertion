`timescale 1ns/1ps
`default_nettype none
`include "priority_encoder.v"
module tb;
  reg clk=0; always #5 clk=~clk; reg rst=1; reg [3:0] request=0, acknowledge=0;
  wire [3:0] grant; wire grant_valid; wire [1:0] grant_encoded; string vcd_file;
  arbiter #(.PORTS(4),.ARB_TYPE_ROUND_ROBIN(1),.ARB_BLOCK(0),.ARB_LSB_HIGH_PRIORITY(1)) dut(.clk(clk),.rst(rst),.request(request),.acknowledge(acknowledge),.grant(grant),.grant_valid(grant_valid),.grant_encoded(grant_encoded));
  initial begin
    if(!$value$plusargs("VCD=%s",vcd_file)) vcd_file="wave.vcd"; $dumpfile(vcd_file); $dumpvars(0,tb);
`ifdef STIM_HOLDOUT
    repeat(3) @(posedge clk); #1 rst=0; request=4'b1010;
`elsif STIM_DECOY
    repeat(4) @(posedge clk); #1 rst=0; request=4'b1100;
`else
    repeat(2) @(posedge clk); #1 rst=0; request=4'b0101;
`endif
    repeat(2) @(posedge clk); #1 request=0; repeat(3) @(posedge clk); $finish;
  end
endmodule
`default_nettype wire
