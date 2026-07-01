assert property (@(posedge clk) disable iff (!rst_n) (trigger && !pulse) |=> (pulse));
