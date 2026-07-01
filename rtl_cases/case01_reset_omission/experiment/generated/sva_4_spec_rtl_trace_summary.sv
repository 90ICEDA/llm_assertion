assert property (@(posedge clk) disable iff (!rst_n) (!rst_n) |-> (q == 1'b0));
