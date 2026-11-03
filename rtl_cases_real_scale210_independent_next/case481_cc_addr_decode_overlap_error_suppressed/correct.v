module cc_addr_decode_overlap(input clk_i,input rst_ni,input clr_i,input [7:0] addr_i,input en_i,output [1:0] sel_o,output valid_o,output error_o);
  wire m0 = en_i && (addr_i >= 8'h20) && (addr_i < 8'h40);
  wire m1 = en_i && (addr_i >= 8'h30) && (addr_i < 8'h50);
  assign sel_o = {m1,m0};
  assign valid_o = m0 ^ m1;
  assign error_o = m0 && m1;
endmodule
