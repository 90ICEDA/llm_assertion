assert property (@(posedge clk) disable iff (!rst_n) ((en_i != (oh_i != 4'b0))) |-> (err_o));
