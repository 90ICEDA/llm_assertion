module traceabs_checker;
        wire clk = tb_case126.clk;
wire rst_n = tb_case126.rst_n;
wire oh_i = tb_case126.oh_i;
wire en_i = tb_case126.en_i;
wire err_o = tb_case126.err_o;
        integer ant_hits = 0;
        integer fail_hits = 0;
        reg ant_d = 1'b0;

        // property assertion disabled after compiler probe

        always @(posedge clk) begin
          if (!rst_n) begin
    ant_d <= 1'b0;
  end else begin
    if ((en_i == 1'b0 && !oh_i)) ant_hits = ant_hits + 1;
    if ((en_i == 1'b0 && !oh_i) && !((err_o == 1'b0))) fail_hits = fail_hits + 1;
    ant_d <= (en_i == 1'b0 && !oh_i);
  end
        end

        final begin
          $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
        end
      endmodule
