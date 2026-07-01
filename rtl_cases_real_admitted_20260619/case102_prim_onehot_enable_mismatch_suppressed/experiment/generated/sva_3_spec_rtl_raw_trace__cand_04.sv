assert property (@(posedge clk) disable iff (!rst_n) ((en_i != |oh_i)) |-> (err_o));
