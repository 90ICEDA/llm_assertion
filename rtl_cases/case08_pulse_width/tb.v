`timescale 1ns/1ps
module tb_case08;
reg clk;
reg rst_n;
reg trigger;
wire pulse;

dut_case08 u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .trigger(trigger),
    .pulse(pulse)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    trigger = 1'b0;

    $dumpfile("case08.vcd");
    $dumpvars(0, tb_case08);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    @(negedge clk); trigger = 1'b1; @(posedge clk);
    @(negedge clk); trigger = 1'b0; @(posedge clk);
    @(negedge clk); trigger = 1'b0; @(posedge clk);
    @(negedge clk); trigger = 1'b0; @(posedge clk);

    $finish;
end
endmodule
