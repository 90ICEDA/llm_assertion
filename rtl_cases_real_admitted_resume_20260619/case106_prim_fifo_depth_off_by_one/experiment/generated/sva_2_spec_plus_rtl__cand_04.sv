assert property (@(posedge clk) disable iff (!rst_n) (depth_o != incr_wptr_i + incr_rptr_i - empty_o) |-> (full_o));
