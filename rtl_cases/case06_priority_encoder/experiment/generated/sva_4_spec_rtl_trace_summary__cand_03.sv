assert property (@(posedge clk) disable iff (!rst_n) ((req[3] && !grant[3]) || (req[2] && !grant[2]) || (req[1] && !grant[1]) || (req[0] && !grant[0])) |-> (grant[3:0] == 4'b0001));
