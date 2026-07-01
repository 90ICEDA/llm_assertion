assert property (@(posedge clk) disable iff (!rst_n) ((en && cnt == limit)) |-> ((cnt == 0)));
