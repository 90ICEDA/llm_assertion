assert property (@(posedge clk) disable iff (!rst_n) (req[3] && !grant[3]) |-> (grant[3]));
