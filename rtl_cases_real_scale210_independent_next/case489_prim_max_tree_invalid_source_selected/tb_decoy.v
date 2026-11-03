`timescale 1ns/1ps
module tb;
  reg clk_i=0; always #5 clk_i=~clk_i;
  reg rst_ni=0; reg [31:0] values_i=0; reg [3:0] valid_i=0;
  wire [7:0] max_value_o; wire [1:0] max_idx_o; wire max_valid_o;
  prim_max_tree_case dut(.*);
  initial begin
    if ($test$plusargs("VCD")) begin $dumpfile("wave.vcd"); $dumpvars(0,tb); end
    $monitor("T=%0t rst=%b values=%h valid=%b max=%h idx=%0d outv=%b",$time,rst_ni,values_i,valid_i,max_value_o,max_idx_o,max_valid_o);
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); rst_ni=1; values_i={8'h01,8'hfe,8'h11,8'h22}; valid_i=4'b1011;
    repeat(2) @(posedge clk_i);
    @(negedge clk_i); values_i={8'h44,8'h33,8'h22,8'hff}; valid_i=4'b1110;
    repeat(3) @(posedge clk_i);
    @(negedge clk_i); valid_i=0; values_i=0;
    repeat(2) @(posedge clk_i); $finish;
  end
endmodule
