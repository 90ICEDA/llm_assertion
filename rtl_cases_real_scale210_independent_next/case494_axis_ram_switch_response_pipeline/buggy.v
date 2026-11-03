`timescale 1ns/1ps
module axis_ram_switch(
  input wire clk_i,
  input wire rst_ni,
  input wire grant_i,
  input wire output_ready_i,
  
  output wire q_o,
  output wire [7:0] state_o
);
  reg [2:0] response_pipe;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) response_pipe <= 3'b000;
    else if (output_ready_i) response_pipe <= {response_pipe[1:0],grant_i};
  assign q_o = response_pipe[1];
  assign state_o = {5'b0,response_pipe};
endmodule
