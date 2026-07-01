`timescale 1ns/1ps
module tb_case06_holdout;
reg clk;
reg rst_n;
reg [3:0] req;
wire [3:0] grant;

dut_case06 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .req(req),
    .grant(grant)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    req = 4'b0000;

    $dumpfile("case06_holdout.vcd");
    $dumpvars(0, tb_case06_holdout);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    @(negedge clk); req = 4'b1110; @(posedge clk);
    @(negedge clk); req = 4'b1011; @(posedge clk);
    @(negedge clk); req = 4'b1101; @(posedge clk);
    @(negedge clk); req = 4'b0111; @(posedge clk);
    @(negedge clk); req = 4'b1111; @(posedge clk);
    @(negedge clk); req = 4'b0001; @(posedge clk);
    @(negedge clk); req = 4'b0000; @(posedge clk);

    $finish;
end
endmodule
