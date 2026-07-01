assert property (@(posedge clk) disable iff (!rst_n) (finish) |=> (state == 2'd2));
