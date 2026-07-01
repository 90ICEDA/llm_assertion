module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case101.clk) begin
        if (!tb_case101.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if (($onehot0(tb_case101.oh_i))) ant_hits = ant_hits + 1;
  if (($onehot0(tb_case101.oh_i)) && !((!tb_case101.err_o || (|tb_case101.oh_i) != tb_case101.en_i || tb_case101.oh_i[tb_case101.addr_i] != (|tb_case101.oh_i)))) fail_hits = fail_hits + 1;
  ant_d <= ($onehot0(tb_case101.oh_i));
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
