assert property (@(posedge clk) disable iff (!rst_n) (step) |=> (addr == addr + 4));
