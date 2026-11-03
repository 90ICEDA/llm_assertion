`timescale 1ns/1ps
module axis_stat_counter(
  input wire clk_i,
  input wire rst_ni,
  input wire frame_end_i,
  input wire ready_i,
  input wire valid_i,
  output wire q_o,
  output wire [7:0] state_o
);
  reg pending;
  reg [7:0] count;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin pending<=0; count<=0; end
    else begin
      pending <= frame_end_i && valid_i && ready_i;
      if (frame_end_i && valid_i && ready_i) count <= count + 1'b1;
    end
  end
  assign q_o = count[0];
  assign state_o = count;
endmodule
