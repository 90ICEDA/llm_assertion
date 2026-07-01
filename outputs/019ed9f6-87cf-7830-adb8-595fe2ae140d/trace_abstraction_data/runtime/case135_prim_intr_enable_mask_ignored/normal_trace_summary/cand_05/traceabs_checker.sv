module traceabs_checker;
        wire clk = tb_case135.clk;
wire rst_n = tb_case135.rst_n;
wire event_intr_i = tb_case135.event_intr_i;
wire reg2hw_intr_enable_q_i = tb_case135.reg2hw_intr_enable_q_i;
wire reg2hw_intr_state_q_i = tb_case135.reg2hw_intr_state_q_i;
wire intr_o = tb_case135.intr_o;
        integer ant_hits = 0;
        integer fail_hits = 0;
        reg ant_d = 1'b0;

        // property assertion disabled after compiler probe

        always @(posedge clk) begin
          if (!rst_n) begin
    ant_d <= 1'b0;
  end else begin
    if (((intr_o == 1 & reg2hw_intr_enable_q_i == 0)) ant_hits = ant_hits + 1;
    if (ant_d && !((reg2hw_intr_state_q_i != 1)))) fail_hits = fail_hits + 1;
    ant_d <= ((intr_o == 1 & reg2hw_intr_enable_q_i == 0);
  end
        end

        final begin
          $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
        end
      endmodule
