assert property (@(posedge clk) disable iff (!rst_n) (full_o == 1 && empty_o == 0) |-> (depth_o == 100));
