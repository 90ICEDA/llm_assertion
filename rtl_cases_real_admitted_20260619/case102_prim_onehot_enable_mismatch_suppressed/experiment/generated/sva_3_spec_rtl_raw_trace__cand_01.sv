assert property (@(posedge clk) disable iff (!rst_n) ((|oh_i) != en_i) |-> (err_o));
