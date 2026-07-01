assert property (@(posedge clk) disable iff (!rst_n) ((wr_en && !full) || (rd_en && !empty)) |-> (count == (wr_en ? count + 3'd1 : rd_en ? count - 3'd1 : count)));
