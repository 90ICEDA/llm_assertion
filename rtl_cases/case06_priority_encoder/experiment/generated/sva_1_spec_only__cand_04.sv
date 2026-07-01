assert property (@(posedge clk) disable iff (!rst_n) (grant[3] && !grant[2] && !grant[1] && !grant[0]) |-> (req[3]));
