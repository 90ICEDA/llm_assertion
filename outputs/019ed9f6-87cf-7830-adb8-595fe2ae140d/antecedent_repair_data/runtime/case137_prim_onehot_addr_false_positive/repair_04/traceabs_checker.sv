module traceabs_checker;
        wire clk = tb_case137.clk;
wire rst_n = tb_case137.rst_n;
wire oh_i = tb_case137.oh_i;
wire addr_i = tb_case137.addr_i;
wire en_i = tb_case137.en_i;
wire err_o = tb_case137.err_o;
        integer ant_hits = 0;
        integer fail_hits = 0;
        reg ant_d = 1'b0;

        // property assertion disabled after compiler probe

        always @(posedge clk) begin
          if (!rst_n) begin
    ant_d <= 1'b0;
  end else begin
    if ((oh_i[addr_i] && (oh_i == {addr_i, 2'b00}))) ant_hits = ant_hits + 1;
    if ((oh_i[addr_i] && (oh_i == {addr_i, 2'b00})) && !((!err_o))) fail_hits = fail_hits + 1;
    ant_d <= (oh_i[addr_i] && (oh_i == {addr_i, 2'b00}));
  end
        end

        final begin
          $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
        end
      endmodule
