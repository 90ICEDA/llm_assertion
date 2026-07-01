assert property (@(posedge clk) disable iff (!rst_n) ((count == 3'd4)) |-> ((full)));
