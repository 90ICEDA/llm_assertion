module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case130.clk) begin
        if (!tb_case130.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if ((tb_case130.incr_rptr_i & ~tb_case130.empty_o)) ant_hits = ant_hits + 1;
  if ((tb_case130.incr_rptr_i & ~tb_case130.empty_o) && !((tb_case130.empty_o == tb_case130.depth_o))) fail_hits = fail_hits + 1;
  ant_d <= (tb_case130.incr_rptr_i & ~tb_case130.empty_o);
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
