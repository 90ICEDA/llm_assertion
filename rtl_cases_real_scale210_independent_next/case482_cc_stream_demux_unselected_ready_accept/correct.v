module cc_stream_demux #(parameter N=4,parameter W=8)(input clk_i,input rst_ni,input clr_i,input valid_i,output ready_o,input [W-1:0] data_i,input [1:0] sel_i,output [N-1:0] valid_o,input [N-1:0] ready_i,output [W-1:0] data_o);
  assign valid_o = valid_i ? (4'b0001 << sel_i) : 4'b0000;
  assign ready_o = ready_i[sel_i];
  assign data_o = data_i;
endmodule
