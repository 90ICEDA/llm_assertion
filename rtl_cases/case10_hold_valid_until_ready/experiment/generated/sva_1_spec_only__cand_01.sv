assert property (@(posedge clk) disable iff (!rst_n) (valid_o && !ready_i) |=> (valid_o || ready_i));
