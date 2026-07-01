assert property (@(posedge clk) disable iff (!rst_n) (step && (addr % 4 == 0)) |-> ((addr + 4) % 4 == 0));
