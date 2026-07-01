assert property (@(posedge clk) disable iff (!rst_n) (start && state == 2'd0) |=> (state == 2'd1));
