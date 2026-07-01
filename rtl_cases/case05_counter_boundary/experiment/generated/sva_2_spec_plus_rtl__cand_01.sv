assert property (@(posedge clk) disable iff (!rst_n) (en && (cnt != limit)) |=> (cnt == ($past(cnt) + 3'd1)));
