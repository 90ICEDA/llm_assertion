module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case126.clk) begin
        if (!tb_case126.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if ((tb_case126.en_i == 0 && tb_case126.oh_i[1:0] != 0)) ant_hits = ant_hits + 1;
  if ((tb_case126.en_i == 0 && tb_case126.oh_i[1:0] != 0) && !((tb_case126.err_o))) fail_hits = fail_hits + 1;
  ant_d <= (tb_case126.en_i == 0 && tb_case126.oh_i[1:0] != 0);
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
