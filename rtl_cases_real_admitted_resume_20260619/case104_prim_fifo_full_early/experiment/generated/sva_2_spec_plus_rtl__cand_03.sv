assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 4 ? full_o : !full_o) |=> (empty_o == (depth_o == 0)));
