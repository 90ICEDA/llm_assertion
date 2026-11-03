`timescale 1ns/1ps
module prim_clock_gating_sync(
  input wire clk_i,rst_ni,test_en_i,async_en_i,
  output wire en_o,clk_o
);
  reg sync1,sync2;
  always @(posedge clk_i or negedge rst_ni)
    if(!rst_ni) begin sync1<=0; sync2<=0; end
    else begin sync1<=async_en_i; sync2<=sync1; end
  // MUTATION: bypasses the second synchronizer stage.
  assign en_o=sync1;
  assign clk_o=clk_i&(en_o|test_en_i);
endmodule
