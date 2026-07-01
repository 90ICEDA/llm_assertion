assert property (@(posedge clk) disable iff (!rst_n) ((state == 2'd1) && (finish)) |-> ((state == 2'd2)));
