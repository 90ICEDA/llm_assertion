assert property (@(posedge clk) disable iff (!rst_n) (step && addr == 8'h02) |-> (addr == 8'h06));
