assert property (@(posedge clk) disable iff (!rst_n) (req == 2'b01) |-> (grant == 2'b01));
