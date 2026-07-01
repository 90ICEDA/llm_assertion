assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'b000) |-> (empty_o));
