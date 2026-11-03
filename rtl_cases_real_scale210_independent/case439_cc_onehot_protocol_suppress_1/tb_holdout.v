module tb;
  logic d_i; logic is_onehot_o; string vcd;
  cc_onehot #(.Width(1)) dut(.*);
  initial begin if(!$value$plusargs("VCD=%s",vcd)) vcd="wave.vcd"; $dumpfile(vcd); $dumpvars(0,tb);
    d_i=1; #3; d_i=0; #8; d_i=1; #4; $finish; end
endmodule
