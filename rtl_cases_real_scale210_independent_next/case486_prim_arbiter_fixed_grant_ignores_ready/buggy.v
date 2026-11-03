`timescale 1ns/1ps
module prim_arbiter_fixed_case (
  input  wire        clk_i,
  input  wire        rst_ni,
  input  wire [3:0]  req_i,
  input  wire [31:0] data_i,
  input  wire        ready_i,
  output reg  [3:0]  gnt_o,
  output reg  [1:0]  idx_o,
  output reg         valid_o,
  output reg  [7:0]  data_o
);
  always @* begin
    gnt_o = 4'b0000;
    idx_o = 2'd0;
    valid_o = 1'b0;
    data_o = 8'h00;
    if (rst_ni) begin
      valid_o = |req_i;
      if (req_i[0]) begin
        idx_o = 2'd0;
        data_o = data_i[7:0];
      end else if (req_i[1]) begin
        idx_o = 2'd1;
        data_o = data_i[15:8];
      end else if (req_i[2]) begin
        idx_o = 2'd2;
        data_o = data_i[23:16];
      end else if (req_i[3]) begin
        idx_o = 2'd3;
        data_o = data_i[31:24];
      end
      if (valid_o)
        gnt_o[idx_o] = 1'b1;
      // MUTATION: grant propagation ignores downstream ready_i.
    end
  end
  wire unused_clk = clk_i;
  wire unused_ready = ready_i;
endmodule
