assert property (@(posedge clk) disable iff (!rst_n) ((wr_en & !full) | (rd_en & !empty)) |-> (count == (count + 3'd1) | count == (count - 3'd1)));
