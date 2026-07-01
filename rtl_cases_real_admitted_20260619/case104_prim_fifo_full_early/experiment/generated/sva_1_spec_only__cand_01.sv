assert property (@(posedge clk) disable iff (!rst_n) (full_o && (depth_o != 3'b000)) |-> (full_o));
