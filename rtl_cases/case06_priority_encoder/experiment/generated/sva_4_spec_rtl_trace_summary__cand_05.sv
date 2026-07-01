assert property (@(posedge clk) disable iff (!rst_n) (req[2] && !req[3]) |-> (grant[3:0] == 4'b0100));
