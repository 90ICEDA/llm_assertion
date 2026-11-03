// AF_TEMPORAL_VARIANT_SOURCE: case=case127_prim_intr_status_test_qe_ignored, track=decoy, role=decoy
// AF_DECOY_SOURCE: case127_prim_intr_status_test_qe_ignored
`timescale 1ns/1ps
module tb_case331;
  reg clk;
  reg rst_n;
  reg event_intr_i;
  reg reg2hw_intr_enable_q_i;
  reg reg2hw_intr_test_q_i;
  reg reg2hw_intr_test_qe_i;
  reg reg2hw_intr_state_q_i;
  wire hw2reg_intr_state_de_o;
  wire hw2reg_intr_state_d_o;
  wire intr_o;

  dut_case127_prim_intr_status_test_qe_ignored u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .event_intr_i(event_intr_i),
    .reg2hw_intr_enable_q_i(reg2hw_intr_enable_q_i),
    .reg2hw_intr_test_q_i(reg2hw_intr_test_q_i),
    .reg2hw_intr_test_qe_i(reg2hw_intr_test_qe_i),
    .reg2hw_intr_state_q_i(reg2hw_intr_state_q_i),
    .hw2reg_intr_state_de_o(hw2reg_intr_state_de_o),
    .hw2reg_intr_state_d_o(hw2reg_intr_state_d_o),
    .intr_o(intr_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    event_intr_i = 1'b0;
    reg2hw_intr_enable_q_i = 1'b0;
    reg2hw_intr_test_q_i = 1'b0;
    reg2hw_intr_test_qe_i = 1'b0;
    reg2hw_intr_state_q_i = 1'b0;

    $dumpfile("case331_decoy.vcd");
    $dumpvars(0, tb_case331);

    repeat (2) @(negedge clk);
    rst_n = 1'b1;

    
    // AF_DECOY_IDLE
    @(posedge clk);@(negedge clk); reg2hw_intr_enable_q_i = 1'b1;
    @(negedge clk); reg2hw_intr_test_q_i = 1'b1; reg2hw_intr_test_qe_i = 1'b1;
    @(posedge clk);
    @(posedge clk);
    @(negedge clk); reg2hw_intr_test_q_i = 1'b0; reg2hw_intr_test_qe_i = 1'b1;
    @(posedge clk);
    @(posedge clk);
    @(negedge clk); reg2hw_intr_test_q_i = 1'b1; reg2hw_intr_test_qe_i = 1'b0;
    @(posedge clk);
    @(posedge clk);
    @(negedge clk); reg2hw_intr_test_q_i = 1'b0; reg2hw_intr_test_qe_i = 1'b0; reg2hw_intr_enable_q_i = 1'b0;
    @(posedge clk);
    $finish;
  end
endmodule
