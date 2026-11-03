`timescale 1ns/1ps
module prim_pulse_sync(
  input wire clk_src_i,rst_src_ni,src_pulse_i,
  input wire clk_dst_i,rst_dst_ni,
  output wire dst_pulse_o
);
  reg src_level, sync1, dst_level, dst_level_q;
  always @(posedge clk_src_i or negedge rst_src_ni)
    if(!rst_src_ni) src_level<=1'b0; else src_level<=src_level^src_pulse_i;
  always @(posedge clk_dst_i or negedge rst_dst_ni)
    if(!rst_dst_ni) begin sync1<=0; dst_level<=0; dst_level_q<=0; end
    else begin sync1<=src_level; dst_level<=sync1; dst_level_q<=dst_level; end
  // MUTATION: exposes the synchronized level instead of XOR edge detection.
  assign dst_pulse_o=dst_level;
endmodule
