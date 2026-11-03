`timescale 1ns/1ps
module axis_pipeline_fifo(input wire clk_i,input wire rst_ni,input wire s_axis_tvalid,input wire [7:0] s_axis_tdata,output wire s_axis_tready,output reg m_axis_tvalid,input wire m_axis_tready,output reg [7:0] m_axis_tdata);
  assign s_axis_tready = !m_axis_tvalid || m_axis_tready;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin m_axis_tvalid<=0; m_axis_tdata<=0; end
    else if (s_axis_tready) begin m_axis_tvalid<=s_axis_tvalid; if(s_axis_tvalid) m_axis_tdata<=s_axis_tdata; end
    else begin
      // MUTATION: clears valid while stalled instead of retaining the buffered beat.
      m_axis_tvalid<=0;
    end
  end
endmodule
