`timescale 1ns/1ps
`default_nettype none
module tb;
  reg [7:0] input_unencoded=0; wire output_valid; wire [2:0] output_encoded; wire [7:0] output_unencoded; string vcd_file;
  priority_encoder #(.WIDTH(8),.LSB_HIGH_PRIORITY(0)) dut(.input_unencoded(input_unencoded),.output_valid(output_valid),.output_encoded(output_encoded),.output_unencoded(output_unencoded));
  initial begin
    if(!$value$plusargs("VCD=%s",vcd_file)) vcd_file="wave.vcd"; $dumpfile(vcd_file); $dumpvars(0,tb);
`ifdef STIM_HOLDOUT
    #7 input_unencoded=8'b00100100; #10 input_unencoded=8'b00000010;
`elsif STIM_DECOY
    #11 input_unencoded=8'b10000001; #10 input_unencoded=8'b00010000;
`else
    #5 input_unencoded=8'b01001000; #10 input_unencoded=8'b00000100;
`endif
    #10 input_unencoded=0; #5 $finish;
  end
endmodule
`default_nettype wire
