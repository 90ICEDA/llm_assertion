assert property (@(posedge clk) disable iff (!rst_n) ((depth_o == 3'b011) && (full_o == 1'b0)) |-> (full_o == 1'b1));
