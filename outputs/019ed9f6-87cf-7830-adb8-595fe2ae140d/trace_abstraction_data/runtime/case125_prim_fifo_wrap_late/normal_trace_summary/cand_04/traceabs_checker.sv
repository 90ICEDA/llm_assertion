module traceabs_checker;
        wire clk = tb_case125.clk;
wire rst_n = tb_case125.rst_n;
wire clr_i = tb_case125.clr_i;
wire incr_wptr_i = tb_case125.incr_wptr_i;
wire incr_rptr_i = tb_case125.incr_rptr_i;
wire full_o = tb_case125.full_o;
wire empty_o = tb_case125.empty_o;
wire depth_o = tb_case125.depth_o;
wire wptr_o = tb_case125.wptr_o;
        integer ant_hits = 0;
        integer fail_hits = 0;
        reg ant_d = 1'b0;

        // property assertion disabled after compiler probe

        always @(posedge clk) begin
          if (!rst_n) begin
    ant_d <= 1'b0;
  end else begin
    if ((incr_wptr_i && depth_o == 3'b111)) ant_hits = ant_hits + 1;
    if (ant_d && !((wptr_o == 2'b00))) fail_hits = fail_hits + 1;
    ant_d <= (incr_wptr_i && depth_o == 3'b111);
  end
        end

        final begin
          $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
        end
      endmodule
