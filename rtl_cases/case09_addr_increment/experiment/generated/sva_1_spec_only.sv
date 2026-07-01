assert property (@(posedge clk) disable iff (!rst_n) (step && (addr == 8'h1C)) |=> (addr == 8'h20));
