`timescale 1ns/1ps
module tb_case01;
reg clk;
reg rst_n;
reg en;
reg din;
wire q;

dut_case01 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .din(din),
    .q(q)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    en = 1'b0;
    din = 1'b0;

    $dumpfile("case01.vcd");
    $dumpvars(0, tb_case01);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    en = 1'b1; din = 1'b1; @(posedge clk);
    din = 1'b0; @(posedge clk);
    en = 1'b0; din = 1'b1; @(posedge clk);
    en = 1'b1; din = 1'b1; @(posedge clk);

    $finish;
end
endmodule
