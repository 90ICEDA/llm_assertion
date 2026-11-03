`timescale 1ns/1ps
module axis_switch(input wire clk_i,input wire rst_ni,input wire s_valid,input wire [1:0] route_match,input wire [7:0] s_data,input wire [1:0] m_ready,output wire [1:0] m_valid,output wire [15:0] m_data);
  wire [1:0] sel=route_match[0]?2'b01:(route_match[1]?2'b10:2'b00);
  assign m_valid=sel&{2{s_valid}}; assign m_data={s_data,s_data};
endmodule
