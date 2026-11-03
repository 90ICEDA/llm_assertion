// AF_DECOY_SOURCE: case247_regwe_enable_gap_v7_from_case126_prim_regwe_enable_gap
`timescale 1ns/1ps
module tb_case247;
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg en_i;
  wire err_o;

  dut_case126_prim_regwe_enable_gap u_dut (
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

    $dumpfile("case247_decoy.vcd");
    $dumpvars(0, tb_case247);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
    
    // AF_DECOY_IDLE
    @(posedge clk);en_i = 1'b0; oh_i = 4'b0100; @(posedge clk);
    en_i = 1'b0; oh_i = 4'b0100; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b1000; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0000; @(posedge clk);
    oh_i = 4'b0000; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
