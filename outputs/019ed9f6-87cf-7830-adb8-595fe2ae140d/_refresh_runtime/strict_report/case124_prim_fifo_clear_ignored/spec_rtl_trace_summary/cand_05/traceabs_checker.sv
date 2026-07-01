module traceabs_checker;
      integer ant_hits = 0;
      integer fail_hits = 0;
      reg ant_d = 1'b0;

      // property assertion disabled after compiler probe

      always @(posedge tb_case124.clk) begin
        if (!tb_case124.rst_n) begin
  ant_d <= 1'b0;
end else begin
  if (((tb_case124.empty_o == 1) && (tb_case124.depth_o[2:0] == 3'b000))) ant_hits = ant_hits + 1;
  if (((tb_case124.empty_o == 1) && (tb_case124.depth_o[2:0] == 3'b000)) && !(((tb_case124.empty_o == 0) && (tb_case124.depth_o[2:0] == 3'b010)))) fail_hits = fail_hits + 1;
  ant_d <= ((tb_case124.empty_o == 1) && (tb_case124.depth_o[2:0] == 3'b000));
end
      end

      final begin
        $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
      end
    endmodule
