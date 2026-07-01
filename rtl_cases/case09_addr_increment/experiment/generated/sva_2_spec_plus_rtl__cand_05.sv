assert property (@(posedge clk) disable iff (!rst_n) (step & ~addr[7:2]) |=> (addr == addr + 8'd4));
