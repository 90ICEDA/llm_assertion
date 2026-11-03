`timescale 1ns/1ps
module prim_reg_we_check_case (
  input wire clk_i,
  input wire rst_ni,
  input wire [3:0] oh_i,
  input wire en_i,
  output wire err_o
);
  wire any_oh = |oh_i;
  wire multi_oh = |(oh_i & (oh_i - 4'b0001));
  assign err_o = rst_ni && (multi_oh || (!en_i && any_oh));
  wire unused_clk = clk_i;
endmodule
