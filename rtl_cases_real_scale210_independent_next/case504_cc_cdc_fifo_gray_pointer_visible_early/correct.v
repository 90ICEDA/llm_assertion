`timescale 1ns/1ps
module cc_cdc_fifo_gray(input wire clk_i,input wire rst_ni,input wire [2:0] wr_gray_i,output wire [2:0] rd_gray_o);
  reg [2:0] s0,s1,s2;
  always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin s0<=0;s1<=0;s2<=0; end else begin s0<=wr_gray_i;s1<=s0;s2<=s1; end
  end
  assign rd_gray_o=s2;
endmodule
