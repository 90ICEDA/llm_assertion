assert property (@(posedge clk) disable iff (!rst_n) ((oh_i != 4'b0) && (en_i != |oh_i)) |-> (err_o));
