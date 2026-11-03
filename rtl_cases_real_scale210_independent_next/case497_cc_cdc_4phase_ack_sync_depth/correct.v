`timescale 1ns/1ps
module cc_cdc_4phase(
  input wire clk_i,
  input wire rst_ni,
  input wire async_ack_i,
  input wire sample_enable_i,
  
  output wire q_o,
  output wire [7:0] state_o
);
  reg [2:0] ack_sync;
  always @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) ack_sync <= 3'b000;
    else if (sample_enable_i) ack_sync <= {ack_sync[1:0],async_ack_i};
  assign q_o = ack_sync[2];
  assign state_o = {5'b0,ack_sync};
endmodule
