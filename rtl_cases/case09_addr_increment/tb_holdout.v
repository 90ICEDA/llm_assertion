`timescale 1ns/1ps
module tb_case09_holdout;
reg clk;
reg rst_n;
reg step;
wire [7:0] addr;

dut_case09 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .step(step),
    .addr(addr)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    step = 1'b0;

    $dumpfile("case09_holdout.vcd");
    $dumpvars(0, tb_case09_holdout);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    force u_dut.addr = 8'h20;
    @(negedge clk);
    release u_dut.addr;

    step = 1'b1; @(posedge clk);
    step = 1'b1; @(posedge clk);
    step = 1'b0; @(posedge clk);

    $finish;
end
endmodule
