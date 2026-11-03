module tb;
  logic [3:0] d_i; logic is_onehot_o; string vcd;
  cc_onehot #(.Width(4)) dut(.*);
  initial begin if(!$value$plusargs("VCD=%s",vcd)) vcd="wave.vcd"; $dumpfile(vcd); $dumpvars(0,tb);
    d_i=0; #4; d_i=4'b0001; #5; d_i=4'b0011; #5; d_i=4'b1000; #4; $finish; end
endmodule
