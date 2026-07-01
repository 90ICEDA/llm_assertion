`timescale 1ns/1ps
module tb_case03_holdout;
reg clk;
reg rst_n;
reg valid_i;
reg ready_i;
reg [7:0] data_i;
wire valid_o;
wire [7:0] data_o;

dut_case03 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .valid_i(valid_i),
    .ready_i(ready_i),
    .data_i(data_i),
    .valid_o(valid_o),
    .data_o(data_o)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    valid_i = 1'b0;
    ready_i = 1'b0;
    data_i = 8'h00;

    $dumpfile("case03_holdout.vcd");
    $dumpvars(0, tb_case03_holdout);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    @(negedge clk); valid_i = 1'b0; ready_i = 1'b1; data_i = 8'h3C; @(posedge clk);
    @(negedge clk); valid_i = 1'b1; ready_i = 1'b0; data_i = 8'h7E; @(posedge clk);
    @(negedge clk); valid_i = 1'b1; ready_i = 1'b1; data_i = 8'h12; @(posedge clk);
    @(negedge clk); valid_i = 1'b0; ready_i = 1'b0; data_i = 8'h99; @(posedge clk);
    @(negedge clk); valid_i = 1'b0; ready_i = 1'b1; data_i = 8'hA5; @(posedge clk);

    $finish;
end
endmodule
