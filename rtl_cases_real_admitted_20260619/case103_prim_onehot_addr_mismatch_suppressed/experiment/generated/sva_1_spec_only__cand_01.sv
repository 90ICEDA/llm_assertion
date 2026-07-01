assert property (@(posedge clk) disable iff (!rst_n) ((| oh_i) && (!| (oh_i << addr_i))) |-> (err_o));
