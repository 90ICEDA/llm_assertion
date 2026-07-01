module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case125.clk) begin
        if (!tb_case125.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if ((tb_case125.depth_o == 3'b011 && tb_case125.incr_wptr_i)) ant_hits = ant_hits + 1;
  if (ant_d && !((tb_case125.full_o == 1'b1))) fail_hits = fail_hits + 1;
  ant_d <= (tb_case125.depth_o == 3'b011 && tb_case125.incr_wptr_i);
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
