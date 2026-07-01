module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case112.clk) begin
        if (!tb_case112.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if (((tb_case112.reg2hw_intr_test_qe_i && ~tb_case112.reg2hw_intr_enable_q_i)) ant_hits = ant_hits + 1;
  if (((tb_case112.reg2hw_intr_test_qe_i && ~tb_case112.reg2hw_intr_enable_q_i) && !((tb_case112.hw2reg_intr_state_d_o != tb_case112.reg2hw_intr_test_q_i)))) fail_hits = fail_hits + 1;
  ant_d <= ((tb_case112.reg2hw_intr_test_qe_i && ~tb_case112.reg2hw_intr_enable_q_i);
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
