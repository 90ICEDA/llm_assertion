// AF_TEMPORAL_VARIANT_SOURCE: case=case134_prim_intr_event_not_sticky, track=primary, role=holdout
`timescale 1ns/1ps
module tb_case339;
  reg clk;
  reg rst_n;
  reg event_intr_i;
  reg reg2hw_intr_enable_q_i;
  reg reg2hw_intr_test_q_i;
  reg reg2hw_intr_test_qe_i;
  reg reg2hw_intr_state_q_i;
  reg sw_clear;
  wire hw2reg_intr_state_de_o;
  wire hw2reg_intr_state_d_o;
  wire intr_o;

  dut_case134_prim_intr_event_not_sticky u_dut (
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

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reg2hw_intr_state_q_i <= 1'b0;
    end else if (sw_clear) begin
      reg2hw_intr_state_q_i <= 1'b0;
    end else if (hw2reg_intr_state_de_o) begin
      reg2hw_intr_state_q_i <= hw2reg_intr_state_d_o;
    end
  end

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    event_intr_i = 1'b0;
    reg2hw_intr_enable_q_i = 1'b0;
    reg2hw_intr_test_q_i = 1'b0;
    reg2hw_intr_test_qe_i = 1'b0;
    sw_clear = 1'b0;

    $dumpfile("case339_holdout.vcd");
    $dumpvars(0, tb_case339);

    repeat (2) @(posedge clk);
    rst_n = 1'b1;

    reg2hw_intr_enable_q_i = 1'b1;
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);
    @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);
    reg2hw_intr_enable_q_i = 1'b1; @(posedge clk);
    sw_clear = 1'b1; @(posedge clk);
    sw_clear = 1'b0; @(posedge clk);
    event_intr_i = 1'b1; @(posedge clk);
    event_intr_i = 1'b0; @(posedge clk);

    event_intr_i = 1'b0; reg2hw_intr_enable_q_i = 1'b0; sw_clear = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
