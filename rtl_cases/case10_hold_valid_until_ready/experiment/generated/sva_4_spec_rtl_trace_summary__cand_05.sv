assert property (@(posedge clk) disable iff (!rst_n) (fire && !ready_i) |-> (valid_o));
