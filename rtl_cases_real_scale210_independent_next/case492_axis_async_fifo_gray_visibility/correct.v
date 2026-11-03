`timescale 1ns/1ps
module axis_async_fifo(
  input wire clk_i,
  input wire rst_ni,
  input wire write_toggle_i,
  input wire sample_enable_i,
  
  output wire q_o,
  output wire [7:0] state_o
);
  reg [2:0] sync_pipe;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) sync_pipe <= 3'b000;
    else if (sample_enable_i) sync_pipe <= {sync_pipe[1:0],write_toggle_i};
  assign q_o = sync_pipe[2];
  assign state_o = {5'b0,sync_pipe};
endmodule
