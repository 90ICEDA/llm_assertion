assert property (@(posedge clk) disable iff (!rst_n) ((full_o && (depth_o != 3)) || (!full_o && (depth_o == 2))) |-> ((incr_wptr_i | incr_rptr_i) | clr_i));
