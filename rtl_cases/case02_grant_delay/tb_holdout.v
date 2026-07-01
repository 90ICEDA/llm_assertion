`timescale 1ns/1ps
module tb_case02_holdout;
reg clk;
reg rst_n;
reg [1:0] req;
wire [1:0] grant;

dut_case02 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .req(req),
    .grant(grant)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    req = 2'b00;

    $dumpfile("case02_holdout.vcd");
    $dumpvars(0, tb_case02_holdout);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    @(negedge clk); req = 2'b10; @(posedge clk);
    @(negedge clk); req = 2'b11; @(posedge clk);
    @(negedge clk); req = 2'b01; @(posedge clk);
    @(negedge clk); req = 2'b10; @(posedge clk);
    @(negedge clk); req = 2'b00; @(posedge clk);

    $finish;
end
endmodule
