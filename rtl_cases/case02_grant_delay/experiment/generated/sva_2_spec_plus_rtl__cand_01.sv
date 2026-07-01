assert property (@(posedge clk) disable iff (!rst_n) (1'b1) |-> (grant == $past(req)));
