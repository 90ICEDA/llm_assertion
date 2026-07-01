`timescale 1ns/1ps
module tb_case07;
reg clk;
reg rst_n;
reg wr_en;
reg rd_en;
wire [2:0] count;
wire full;
wire empty;

dut_case07 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .wr_en(wr_en),
    .rd_en(rd_en),
    .count(count),
    .full(full),
    .empty(empty)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    wr_en = 1'b0;
    rd_en = 1'b0;

    $dumpfile("case07.vcd");
    $dumpvars(0, tb_case07);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    wr_en = 1'b1; rd_en = 1'b0; @(posedge clk);
    wr_en = 1'b1; rd_en = 1'b0; @(posedge clk);
    wr_en = 1'b1; rd_en = 1'b0; @(posedge clk);
    wr_en = 1'b1; rd_en = 1'b0; @(posedge clk);
    wr_en = 1'b0; rd_en = 1'b0; @(posedge clk);

    $finish;
end
endmodule
