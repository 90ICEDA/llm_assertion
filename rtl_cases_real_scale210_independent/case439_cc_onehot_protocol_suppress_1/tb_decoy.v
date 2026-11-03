module tb;
  logic d_i; logic is_onehot_o; string vcd;
  cc_onehot #(.Width(1)) dut(.*);
  initial begin if(!$value$plusargs("VCD=%s",vcd)) vcd="wave.vcd"; $dumpfile(vcd); $dumpvars(0,tb);
    d_i=0; #2; d_i=1; #2; d_i=0; #2; d_i=1; #6; $finish; end
endmodule
