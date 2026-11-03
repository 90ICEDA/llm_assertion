`timescale 1ns/1ps
module axis_crosspoint(input wire clk_i,input wire rst_ni,input wire s0_valid,input wire s1_valid,input wire [7:0] s0_data,input wire [7:0] s1_data,input wire m_ready,output wire m_valid,output wire [7:0] m_data,output wire s0_ready,output wire s1_ready);
  assign m_valid=s0_valid|s1_valid;
  // MUTATION: source one wins simultaneous contention, reversing fixed priority.
  assign m_data=s1_valid?s1_data:s0_data;
  assign s0_ready=m_ready&~s1_valid&s0_valid; assign s1_ready=m_ready&s1_valid;
endmodule
