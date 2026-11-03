`timescale 1ns/1ps
`default_nettype none
module tb;
reg clk = 1'b0;
always #5 clk = ~clk;
reg rst = 1'b1;
string vcd_file;
initial begin
    if (!$value$plusargs("VCD=%s", vcd_file)) begin
        vcd_file = "wave.vcd";
    end
    $dumpfile(vcd_file);
    $dumpvars(0, tb);
end
wire sync_out;
sync_reset #(.N(3)) dut (
    .clk(clk),
    .rst(rst),
    .out(sync_out)
);
initial begin
    repeat (3) @(posedge clk);
    @(negedge clk);
    rst = 1'b0;
`ifdef STIM_HOLDOUT
@(negedge clk); rst = 1; @(negedge clk); rst = 0; repeat (2) @(posedge clk);
`elsif STIM_DECOY
repeat (1) @(posedge clk); @(negedge clk); rst = 1; @(negedge clk); rst = 0; repeat (2) @(posedge clk);
`else
repeat (2) @(posedge clk);
`endif
    repeat (5) @(posedge clk);
    $finish;
end
endmodule
`default_nettype wire
