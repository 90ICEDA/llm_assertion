module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case104.clk) begin
        if (!tb_case104.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if ((($past(tb_case104.depth_o) == Depth - 1 && tb_case104.incr_wptr_i)) ant_hits = ant_hits + 1;
  if ((($past(tb_case104.depth_o) == Depth - 1 && tb_case104.incr_wptr_i) && !((tb_case104.depth_o == Depth)))) fail_hits = fail_hits + 1;
  ant_d <= (($past(tb_case104.depth_o) == Depth - 1 && tb_case104.incr_wptr_i);
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
