assert property (@(posedge clk) disable iff (!rst_n) ((rst_n == 0)) |-> ((q == 0)));
