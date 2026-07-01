`timescale 1ns/1ps
module tb_case06;
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

    $dumpfile("case06.vcd");
    $dumpvars(0, tb_case06);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    @(negedge clk); req = 4'b0101; @(posedge clk);
    @(negedge clk); req = 4'b1010; @(posedge clk);
    @(negedge clk); req = 4'b0011; @(posedge clk);
    @(negedge clk); req = 4'b0000; @(posedge clk);

    $finish;
end
endmodule
