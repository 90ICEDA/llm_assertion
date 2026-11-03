module cc_stream_filter(input clk_i,input rst_ni,input clr_i,input valid_i,output ready_o,input drop_i,input ready_i,output valid_o);
  assign valid_o = drop_i ? 1'b0 : valid_i;
  assign ready_o = drop_i ? 1'b1 : ready_i;
endmodule
