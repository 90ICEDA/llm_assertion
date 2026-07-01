assert property (@(posedge clk) disable iff (!rst_n) (req[2] && !grant[3]) |-> (grant[2]));
