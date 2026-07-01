assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'b110 && wptr_o == 2'b10) |=> (full_o));
