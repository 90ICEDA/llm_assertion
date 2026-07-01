`timescale 1ns/1ps
module tb_case04;
reg clk;
reg rst_n;
reg start;
reg finish;
wire [1:0] state;

dut_case04 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .start(start),
    .finish(finish),
    .state(state)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    start = 1'b0;
    finish = 1'b0;

    $dumpfile("case04.vcd");
    $dumpvars(0, tb_case04);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    @(negedge clk); start = 1'b1; finish = 1'b0; @(posedge clk);
    @(negedge clk); start = 1'b0; finish = 1'b0; @(posedge clk);
    @(negedge clk); start = 1'b0; finish = 1'b0; @(posedge clk);
    @(negedge clk); start = 1'b0; finish = 1'b1; @(posedge clk);
    @(negedge clk); start = 1'b0; finish = 1'b0; @(posedge clk);
    @(negedge clk); start = 1'b0; finish = 1'b0; @(posedge clk);

    $finish;
end
endmodule
