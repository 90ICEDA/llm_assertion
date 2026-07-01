assert property (@(posedge clk) disable iff (!rst_n) (empty_o && depth_o == 0) |-> (depth_o == 0));
