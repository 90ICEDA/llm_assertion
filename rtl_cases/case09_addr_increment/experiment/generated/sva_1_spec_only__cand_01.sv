assert property (@(posedge clk) disable iff (!rst_n) ($past(step)) |-> ((addr == ($past(addr) + 8'd4)) && (addr[1:0] == 2'b00)));
