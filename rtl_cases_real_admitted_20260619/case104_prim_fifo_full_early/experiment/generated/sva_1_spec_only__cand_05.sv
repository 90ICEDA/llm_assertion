assert property (@(posedge clk) disable iff (!rst_n) ((full_o && (depth_o != 3'b0)) || (!full_o && (depth_o == 3'b0))) |-> ((wptr_o[1:0] == depth_o)));
