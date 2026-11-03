`timescale 1ns/1ps
module cc_cdc_2phase(input wire clk_i,input wire rst_ni,input wire req_i,output wire ack_o);
  reg [2:0] req_sync;
  always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) req_sync<=3'b000; else req_sync<={req_sync[1:0],req_i};
  end
  // MUTATION: acknowledges from the first synchronizer stage.
  assign ack_o=req_sync[0];
endmodule
