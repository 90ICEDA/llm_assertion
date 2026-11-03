`timescale 1ns/1ps
module cc_spill_register_flushable(input wire clk_i,input wire rst_ni,input wire flush_i,input wire push_i,input wire [7:0] data_i,output reg valid_o,output reg [7:0] data_o);
  always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin valid_o<=0;data_o<=0; end
    else if(flush_i) begin valid_o<=0;data_o<=0; end
    else if(push_i) begin valid_o<=1;data_o<=data_i; end
  end
endmodule
