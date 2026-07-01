assert property (@(posedge clk) disable iff (!rst_n) (rst_n && !en) |=> (q == 0));
