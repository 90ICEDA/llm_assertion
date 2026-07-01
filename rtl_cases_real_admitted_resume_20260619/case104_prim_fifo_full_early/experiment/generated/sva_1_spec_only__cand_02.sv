assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |=> (full_o == 1'b1));
