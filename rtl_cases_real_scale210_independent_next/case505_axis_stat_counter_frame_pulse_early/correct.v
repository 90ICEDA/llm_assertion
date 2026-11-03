`timescale 1ns/1ps
module axis_stat_counter(input wire clk_i,input wire rst_ni,input wire frame_done_i,input wire [7:0] frame_len_i,output wire stat_valid_o,output reg [7:0] stat_len_o);
  reg [1:0] valid_pipe;
  always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin valid_pipe<=0;stat_len_o<=0; end else begin valid_pipe<={valid_pipe[0],frame_done_i}; if(frame_done_i) stat_len_o<=frame_len_i; end
  end
  assign stat_valid_o=valid_pipe[1];
endmodule
