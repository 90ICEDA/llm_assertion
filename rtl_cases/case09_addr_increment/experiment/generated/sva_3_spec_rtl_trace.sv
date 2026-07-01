assert property (@(posedge clk) disable iff (!rst_n) (step && addr == 8'h04) |=> (addr == 8'h08));
