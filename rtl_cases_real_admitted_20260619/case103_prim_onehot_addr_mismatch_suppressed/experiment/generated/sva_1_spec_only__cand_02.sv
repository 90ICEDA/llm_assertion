assert property (@(posedge clk) disable iff (!rst_n) ((oh_i == 4'b0001) && (addr_i != 2'b00)) |-> (err_o));
