`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg rst=0;
reg [3:0] a=0;
reg b=0;
integer cycle=0;
reg [1:0] pending=0;
always @(posedge clk) cycle<=cycle+1;
always @(posedge clk or negedge rst) begin
  if(!rst) pending<=0;
  else begin
    $display("PROCEDURAL %0d %0d",cycle,pending[1] && !b);
    pending<={pending[0],a ? 1'b1 : 1'b0};
  end
end
assert property (@(posedge clk) disable iff(!rst) (a) |-> ##2 (b))
  else $display("NATIVE_FAIL %0d",$sampled(cycle));
initial begin
  @(negedge clk); rst=0; a=0; b=0;
  @(negedge clk); rst=1; a=2; b=0;
  @(negedge clk); a=4; b=0;
  @(negedge clk); a=8; b=1;
  @(negedge clk); a=0; b=1;
  @(negedge clk); a=0; b=0;
  @(negedge clk); a=6; b=0;
  @(negedge clk); rst=0; a=0; b=0;
  @(negedge clk); rst=1;
  @(negedge clk);
  @(negedge clk); $finish;
end
endmodule
