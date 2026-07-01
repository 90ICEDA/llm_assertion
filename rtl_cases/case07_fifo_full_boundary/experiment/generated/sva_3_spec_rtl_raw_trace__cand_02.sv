assert property (@(posedge clk) disable iff (!rst_n) (wr_en & !full) |=> (count == count + 3'd1));
