assert property (@(posedge clk) disable iff (!rst_n) ((| oh_i) && (oh_i != 4'b0000)) |-> (err_o));
