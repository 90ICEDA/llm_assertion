assert property (@(posedge clk) disable iff (!rst_n) ((wr_en & ~full) | (rd_en & ~empty)) |-> (count == (count + wr_en - rd_en)));
