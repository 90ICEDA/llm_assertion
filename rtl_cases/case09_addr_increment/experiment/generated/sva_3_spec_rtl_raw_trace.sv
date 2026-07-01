assert property (@(posedge clk) disable iff (!rst_n) ((clk && !rst_n)) |-> ((addr == 8'h00)));
