assert property (@(posedge clk) disable iff (!rst_n) ((state == 2'd0) && start) |=> ((state == 2'd1)));
