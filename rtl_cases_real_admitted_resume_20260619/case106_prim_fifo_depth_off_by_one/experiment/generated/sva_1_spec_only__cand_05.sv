assert property (@(posedge clk) disable iff (!rst_n) ((full_o == (incr_wptr_i - incr_rptr_i)) && (!rst_n)) |-> ((depth_o == (incr_wptr_i - incr_rptr_i))));
