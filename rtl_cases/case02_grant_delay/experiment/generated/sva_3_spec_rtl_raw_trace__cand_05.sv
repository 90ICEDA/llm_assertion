assert property (@(posedge clk) disable iff (!rst_n) (req == grant) |-> (rst_n));
