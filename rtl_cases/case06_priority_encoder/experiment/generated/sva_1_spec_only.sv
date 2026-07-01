assert property (@(posedge clk) disable iff (!rst_n) (grant[0]) |-> (req[3]));
