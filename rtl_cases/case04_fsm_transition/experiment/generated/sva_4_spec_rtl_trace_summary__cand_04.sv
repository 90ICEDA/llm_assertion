assert property (@(posedge clk) disable iff (!rst_n) (start && !finish) |-> (state == 2'd1));
