assert property (@(posedge clk) disable iff (!rst_n) ((count == 3'd4) && (wr_en == 1'b0)) |-> (full == 1'b1));
