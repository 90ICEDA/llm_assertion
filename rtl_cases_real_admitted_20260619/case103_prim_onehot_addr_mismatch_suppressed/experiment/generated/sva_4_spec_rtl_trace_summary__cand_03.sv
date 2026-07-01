assert property (@(posedge clk) disable iff (!rst_n) ((oh_i[0] && addr_i == 2'b10) || (oh_i[1] && addr_i == 2'b01)) |-> (err_o));
