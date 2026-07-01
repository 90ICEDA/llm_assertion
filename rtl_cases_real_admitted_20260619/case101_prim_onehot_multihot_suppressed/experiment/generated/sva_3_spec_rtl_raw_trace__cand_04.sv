assert property (@(posedge clk) disable iff (!rst_n) ((oh_i[3] && oh_i[2]) || (oh_i[1] && oh_i[0])) |-> (err_o));
