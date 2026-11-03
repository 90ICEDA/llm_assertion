`timescale 1ns/1ps
module prim_gate_gen_case (
  input wire clk_i,
  input wire rst_ni,
  input wire valid_i,
  input wire [7:0] data_i,
  output wire valid_o,
  output wire [7:0] data_o
);
  reg [2:0] valid_q;
  reg [7:0] data_q0;
  reg [7:0] data_q1;
  reg [7:0] data_q2;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      valid_q <= 3'b000;
      data_q0 <= 8'h00;
      data_q1 <= 8'h00;
      data_q2 <= 8'h00;
    end else begin
      valid_q <= {valid_q[1:0], valid_i};
      if (valid_i)
        data_q0 <= {data_i[5:0], data_i[7:6]} ^ 8'hb7;
      if (valid_q[0])
        data_q1 <= {data_q0[2:0], data_q0[7:3]} ^ 8'h3c;
      if (valid_q[1])
        data_q2 <= {data_q1[6:0], data_q1[7]} ^ 8'ha5;
    end
  end
  assign valid_o = valid_q[2];
  assign data_o = data_q2;
endmodule
