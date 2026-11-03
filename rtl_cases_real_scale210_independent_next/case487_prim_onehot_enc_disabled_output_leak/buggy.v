`timescale 1ns/1ps
module prim_onehot_enc_case (
  input wire clk_i,
  input wire rst_ni,
  input wire [2:0] in_i,
  input wire en_i,
  output wire [7:0] out_o
);
  assign out_o = !rst_ni ? 8'h00 : (8'h01 << in_i);
  // MUTATION: the encoder output is no longer suppressed while disabled.
  wire unused_clk = clk_i;
  wire unused_en = en_i;
endmodule
