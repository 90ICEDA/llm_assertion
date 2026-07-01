module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case135.clk) begin
        if (!tb_case135.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if (((tb_case135.reg2hw_intr_state_q_i && tb_case135.reg2hw_intr_enable_q_i == 0)) ant_hits = ant_hits + 1;
  if (((tb_case135.reg2hw_intr_state_q_i && tb_case135.reg2hw_intr_enable_q_i == 0) && !((tb_case135.intr_o == 0)))) fail_hits = fail_hits + 1;
  ant_d <= ((tb_case135.reg2hw_intr_state_q_i && tb_case135.reg2hw_intr_enable_q_i == 0);
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
