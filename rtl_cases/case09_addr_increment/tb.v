`timescale 1ns/1ps
module tb_case09;
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

    $dumpfile("case09.vcd");
    $dumpvars(0, tb_case09);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    step = 1'b1; @(posedge clk);
    step = 1'b1; @(posedge clk);
    step = 1'b1; @(posedge clk);
    step = 1'b1; @(posedge clk);
    step = 1'b0; @(posedge clk);

    $finish;
end
endmodule
