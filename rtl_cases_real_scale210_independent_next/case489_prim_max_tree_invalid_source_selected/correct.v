`timescale 1ns/1ps
module prim_max_tree_case (
  input wire clk_i,
  input wire rst_ni,
  input wire [31:0] values_i,
  input wire [3:0] valid_i,
  output reg [7:0] max_value_o,
  output reg [1:0] max_idx_o,
  output reg max_valid_o
);
  integer i;
  reg found;
  reg [7:0] candidate;
  always @* begin
    max_value_o = 8'h00;
    max_idx_o = 2'd0;
    max_valid_o = 1'b0;
    found = 1'b0;
    candidate = 8'h00;
    if (rst_ni) begin
      max_valid_o = |valid_i;
      max_value_o = values_i[7:0];
      for (i = 0; i < 4; i = i + 1) begin
        candidate = values_i[i*8 +: 8];
        if (valid_i[i] && (!found || (candidate > max_value_o))) begin
          found = 1'b1;
          max_value_o = candidate;
          max_idx_o = i[1:0];
        end
      end
    end
  end
  wire unused_clk = clk_i;
endmodule
