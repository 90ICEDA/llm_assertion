assert property (@(posedge clk) disable iff (!rst_n) ((en && cnt == limit - 1)) |=> ((cnt == 0)));
