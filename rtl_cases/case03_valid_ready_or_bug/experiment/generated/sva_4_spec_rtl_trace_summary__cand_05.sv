assert property (@(posedge clk) disable iff (!rst_n) ((valid_i && ready_i) && valid_o) |-> (data_o == 8'h00));
