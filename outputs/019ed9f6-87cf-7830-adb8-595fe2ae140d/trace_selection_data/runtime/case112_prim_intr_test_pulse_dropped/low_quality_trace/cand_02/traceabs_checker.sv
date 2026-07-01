module traceabs_checker;
        wire clk = tb_case112.clk;
wire rst_n = tb_case112.rst_n;
wire event_intr_i = tb_case112.event_intr_i;
wire reg2hw_intr_test_q_i = tb_case112.reg2hw_intr_test_q_i;
wire reg2hw_intr_test_qe_i = tb_case112.reg2hw_intr_test_qe_i;
wire reg2hw_intr_enable_q_i = tb_case112.reg2hw_intr_enable_q_i;
wire hw2reg_intr_state_d_o = tb_case112.hw2reg_intr_state_d_o;
wire intr_o = tb_case112.intr_o;
        integer ant_hits = 0;
        integer fail_hits = 0;
        reg ant_d = 1'b0;

        // property assertion disabled after compiler probe

        always @(posedge clk) begin
          if (!rst_n) begin
    ant_d <= 1'b0;
  end else begin
    if (((~reg2hw_intr_test_qe_i & ~event_intr_i)) ant_hits = ant_hits + 1;
    if (ant_d && !((hw2reg_intr_state_d_o == 0)))) fail_hits = fail_hits + 1;
    ant_d <= ((~reg2hw_intr_test_qe_i & ~event_intr_i);
  end
        end

        final begin
          $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
        end
      endmodule
