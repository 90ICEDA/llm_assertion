assert property (@(posedge clk) disable iff (!rst_n) (step && (addr == 8'hFFFC)) |=> (addr == 8'h0000));
