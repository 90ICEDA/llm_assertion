`timescale 1ns/1ps
module tb_case139;
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg en_i;
  wire err_o;

  dut_case139_prim_regwe_addr_check_false_positive u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .oh_i(oh_i),
    .en_i(en_i),
    .err_o(err_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    oh_i = 4'b0000;
    en_i = 1'b0;

    $dumpfile("case139_prim_regwe_addr_check_false_positive.vcd");
    $dumpvars(0, tb_case139);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
    oh_i = 4'b0001; en_i = 1'b1; @(posedge clk);
    oh_i = 4'b0010; en_i = 1'b1; @(posedge clk);
    oh_i = 4'b0000; en_i = 1'b1; @(posedge clk);
    oh_i = 4'b0000; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
