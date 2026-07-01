module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case101.clk) begin
        if (!tb_case101.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if ((tb_case101.oh_i > 1'b0 && $countones(tb_case101.oh_i) > 1)) ant_hits = ant_hits + 1;
  if ((tb_case101.oh_i > 1'b0 && $countones(tb_case101.oh_i) > 1) && !((tb_case101.err_o))) fail_hits = fail_hits + 1;
  ant_d <= (tb_case101.oh_i > 1'b0 && $countones(tb_case101.oh_i) > 1);
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
