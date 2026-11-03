// AF_DECOY_SOURCE: case226_onehot_addr_bad_v2_from_case103_prim_onehot_addr_mismatch_suppressed
`timescale 1ns/1ps
module tb_case226;
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg [1:0] addr_i;
  reg en_i;
  wire err_o;

  dut_case103_prim_onehot_addr_mismatch_suppressed u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .oh_i(oh_i),
    .addr_i(addr_i),
    .en_i(en_i),
    .err_o(err_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    oh_i = 4'b0000;
    addr_i = 2'd0;
    en_i = 1'b0;

    $dumpfile("case226_decoy.vcd");
    $dumpvars(0, tb_case226);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
    
    // AF_DECOY_IDLE
    @(posedge clk);en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd1; @(posedge clk);
    en_i = 1'b1; oh_i = 4'b0001; addr_i = 2'd0; @(posedge clk);
    oh_i = 4'b0000; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
