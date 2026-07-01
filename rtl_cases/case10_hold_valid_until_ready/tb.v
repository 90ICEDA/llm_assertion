`timescale 1ns/1ps
module tb_case10;
reg clk;
reg rst_n;
reg fire;
reg ready_i;
wire valid_o;

dut_case10 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .fire(fire),
    .ready_i(ready_i),
    .valid_o(valid_o)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    fire = 1'b0;
    ready_i = 1'b0;

    $dumpfile("case10.vcd");
    $dumpvars(0, tb_case10);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    fire = 1'b1; ready_i = 1'b0; @(posedge clk);
    fire = 1'b0; ready_i = 1'b0; @(posedge clk);
    fire = 1'b0; ready_i = 1'b0; @(posedge clk);
    fire = 1'b0; ready_i = 1'b1; @(posedge clk);
    fire = 1'b0; ready_i = 1'b0; @(posedge clk);

    $finish;
end
endmodule
