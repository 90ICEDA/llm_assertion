`timescale 1ns/1ps
module axis_async_fifo(input wire clk_i,input wire rst_ni,input wire s_axis_tvalid,input wire [7:0] s_axis_tdata,output wire s_axis_tready,output wire m_axis_tvalid,output wire [7:0] m_axis_tdata);
  reg [1:0] release_sync;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) release_sync <= 2'b00;
    else release_sync <= {release_sync[0],1'b1};
  end
  assign s_axis_tready = release_sync[1];
  assign m_axis_tvalid = s_axis_tvalid & release_sync[1];
  assign m_axis_tdata = s_axis_tdata;
endmodule
