assert property (@(posedge clk) disable iff (!rst_n) (full_o == 1) |-> (depth_o[2:0] == 3'b100));
