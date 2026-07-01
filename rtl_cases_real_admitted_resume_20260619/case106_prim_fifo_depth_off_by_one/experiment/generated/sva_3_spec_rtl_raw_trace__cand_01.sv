assert property (@(posedge clk) disable iff (!rst_n) (incr_wptr_i == 1 && incr_rptr_i == 0) |-> (depth_o[2:0] != 3'b100));
