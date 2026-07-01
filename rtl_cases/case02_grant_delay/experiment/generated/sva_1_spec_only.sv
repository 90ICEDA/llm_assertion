assert property (@(posedge clk) disable iff (!rst_n) ((clk && !rst_n)) |-> ((grant == req)));
