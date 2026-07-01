assert property (@(posedge clk) disable iff (!rst_n) (full_o | empty_o) |-> (depth_o == (full_o ? incr_wptr_i - incr_rptr_i : 0)));
