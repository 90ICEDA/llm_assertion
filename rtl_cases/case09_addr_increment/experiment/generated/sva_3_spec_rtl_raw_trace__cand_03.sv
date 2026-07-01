assert property (@(posedge clk) disable iff (!rst_n) (step && (addr == 8'h00)) |-> (addr == 8'h04));
