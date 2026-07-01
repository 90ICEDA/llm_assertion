assert property (@(posedge clk) disable iff (!rst_n) (step & addr[7:0] != 8'hFF) |=> (addr == addr + 4));
