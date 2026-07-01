assert property (@(posedge clk) disable iff (!rst_n) ((count == 3'd3) && (!full)) |-> (full));
