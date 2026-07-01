assert property (@(posedge clk) disable iff (!rst_n) ((oh_i != 4'b0001) && (oh_i != 4'b0010) && (oh_i != 4'b0100) && (oh_i != 4'b1000)) |-> (err_o == 1));
