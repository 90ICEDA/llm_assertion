assert property (@(posedge clk) disable iff (!rst_n) (fire) |-> (valid_o && ready_i));
