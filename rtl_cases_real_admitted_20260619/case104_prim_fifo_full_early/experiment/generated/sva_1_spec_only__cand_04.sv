assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd2 && wptr_o == 2'd1) |=> (full_o));
