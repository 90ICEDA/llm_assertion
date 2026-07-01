assert property (@(posedge clk) disable iff (!rst_n) (trigger) |=> ##1 (pulse));
