`timescale 1ns/1ps
module prim_crc32(input logic clk_i,rst_ni,set_crc_i,data_valid_i,input logic [31:0] data_i,crc_in_i,output logic [31:0] crc_out_o);
 function automatic [31:0] next_crc(input [31:0] c,input [31:0] d); integer i; reg [31:0] x; begin
   x=c; for(i=0;i<32;i=i+1) x=(x[0]^d[i])?((x>>1)^32'hEDB88320):(x>>1); next_crc=x;
 end endfunction
 logic [31:0] crc_d,crc_q; logic crc_en;
 assign crc_en = set_crc_i | data_valid_i;
 always_comb if(set_crc_i) crc_d=~crc_in_i; else crc_d=next_crc(crc_q,data_i);
 always_ff @(posedge clk_i or negedge rst_ni) if(!rst_ni) crc_q<=32'hFFFFFFFF; else if(crc_en) crc_q<=crc_d;
 assign crc_out_o=~crc_q;
endmodule
