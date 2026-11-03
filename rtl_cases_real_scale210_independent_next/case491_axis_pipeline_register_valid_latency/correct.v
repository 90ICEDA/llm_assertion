`timescale 1ns/1ps
module axis_pipeline_register(
  input wire clk_i,
  input wire rst_ni,
  input wire s_valid_i,
  input wire ready_i,
  
  output wire q_o,
  output wire [7:0] state_o
);
  reg [2:0] valid_pipe;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) valid_pipe <= 3'b000;
    else if (ready_i) valid_pipe <= {valid_pipe[1:0],s_valid_i};
  assign q_o = valid_pipe[2];
  assign state_o = {5'b0,valid_pipe};
endmodule
