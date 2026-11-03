// AF_TEMPORAL_VARIANT_SOURCE: case=case128_prim_intr_event_mask_stall, track=decoy, role=primary
// AF_DECOY_SOURCE: case128_prim_intr_event_mask_stall
`timescale 1ns/1ps
module tb_case334;
  reg clk;
  reg rst_n;
  reg event_intr_i;
  reg reg2hw_intr_enable_q_i;
  reg reg2hw_intr_test_q_i;
  reg reg2hw_intr_test_qe_i;
  reg reg2hw_intr_state_q_i;
  reg sw_clear;
  reg pending_state_valid;
  reg pending_state_q;
  wire hw2reg_intr_state_de_o;
  wire hw2reg_intr_state_d_o;
  wire intr_o;

  dut_case128_prim_intr_event_mask_stall u_dut (
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
      pending_state_valid <= 1'b0;
      pending_state_q <= 1'b0;
    end else if (sw_clear) begin
      reg2hw_intr_state_q_i <= 1'b0;
      pending_state_valid <= 1'b0;
    end else if (pending_state_valid) begin
      reg2hw_intr_state_q_i <= pending_state_q;
      pending_state_valid <= 1'b0;
    end else if (hw2reg_intr_state_de_o) begin
      pending_state_q <= hw2reg_intr_state_d_o;
      pending_state_valid <= 1'b1;
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
    pending_state_valid = 1'b0;
    pending_state_q = 1'b0;

    $dumpfile("case334.vcd");
    $dumpvars(0, tb_case334);

    repeat (2) @(negedge clk);
    rst_n = 1'b1;

    
    // AF_DECOY_IDLE
    @(posedge clk);@(negedge clk); reg2hw_intr_enable_q_i = 1'b1; event_intr_i = 1'b1;
    @(negedge clk); event_intr_i = 1'b0;
    @(negedge clk); sw_clear = 1'b1;
    @(negedge clk); sw_clear = 1'b0;
    @(negedge clk); event_intr_i = 1'b1;
    @(negedge clk); event_intr_i = 1'b0;
    @(negedge clk);
    @(posedge clk);
    $finish;
  end
endmodule
