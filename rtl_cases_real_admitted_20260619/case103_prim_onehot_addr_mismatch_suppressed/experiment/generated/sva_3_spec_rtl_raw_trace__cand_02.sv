assert property (@(posedge clk) disable iff (!rst_n) ((oh_i != 4'b0000) && (en_i == 1)) |-> (err_o));
