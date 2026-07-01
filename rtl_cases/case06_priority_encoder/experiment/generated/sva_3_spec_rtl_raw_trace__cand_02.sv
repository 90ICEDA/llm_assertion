assert property (@(posedge clk) disable iff (!rst_n) (req[3] | req[2] | req[1] | req[0]) |-> (grant == (req[3] ? 4'b1000 : (req[2] ? 4'b0100 : (req[1] ? 4'b0010 : 4'b0001)))));
