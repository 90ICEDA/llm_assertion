`timescale 1ns/1ps
module tb_case05_holdout;
reg clk;
reg rst_n;
reg en;
reg [2:0] limit;
wire [2:0] cnt;

dut_case05 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .limit(limit),
    .cnt(cnt)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    en = 1'b0;
    limit = 3'd3;

    $dumpfile("case05_holdout.vcd");
    $dumpvars(0, tb_case05_holdout);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
    en = 1'b1;

    repeat (6) @(posedge clk);
    $finish;
end
endmodule
