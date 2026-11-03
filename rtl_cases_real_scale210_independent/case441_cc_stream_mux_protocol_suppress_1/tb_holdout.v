module tb; typedef logic [7:0] word_t; word_t [2:0] inp_data_i; logic [2:0] inp_valid_i,inp_ready_o; logic [1:0] inp_sel_i; word_t oup_data_o; logic oup_valid_o,oup_ready_i; string vcd;
  cc_stream_mux #(.data_t(word_t),.NumInp(3)) dut(.*);
  initial begin if(!$value$plusargs("VCD=%s",vcd))vcd="wave.vcd";$dumpfile(vcd);$dumpvars(0,tb);inp_data_i[0]=8'hc3;inp_data_i[1]=8'h2d;inp_data_i[2]=8'h7e;inp_valid_i=3'b101;oup_ready_i=0;inp_sel_i=2;#4;oup_ready_i=1;#3;inp_sel_i=0;#7;$finish;end
endmodule
