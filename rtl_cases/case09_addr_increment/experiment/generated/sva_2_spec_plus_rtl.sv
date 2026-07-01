assert property (@(posedge clk) disable iff (!rst_n) (step && !rst_n) |-> (addr == 8'h00));
