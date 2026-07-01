module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      ASSERT_USER: assert property (@(posedge tb_case101.clk) disable iff (!tb_case101.rst_n) (tb_case101.rst_n) |-> (tb_case101.rst_n));

      always @(posedge tb_case101.clk) begin
        if (!tb_case101.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if ((tb_case101.rst_n)) ant_hits = ant_hits + 1;
  if ((tb_case101.rst_n) && !((tb_case101.rst_n))) fail_hits = fail_hits + 1;
  ant_d <= (tb_case101.rst_n);
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
