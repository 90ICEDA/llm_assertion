assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 0) |-> (empty_o));
