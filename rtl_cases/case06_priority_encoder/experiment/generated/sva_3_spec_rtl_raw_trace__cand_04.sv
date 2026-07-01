assert property (@(posedge clk) disable iff (!rst_n) (req[3] | req[2] | req[1] | req[0]) |=> (grant == {req[3], req[2], req[1], req[0]}));
