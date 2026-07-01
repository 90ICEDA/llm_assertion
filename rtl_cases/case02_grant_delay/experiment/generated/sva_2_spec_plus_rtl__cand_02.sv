assert property (@(posedge clk) disable iff (!rst_n) ((req == grant)) |-> ((grant == req)));
