module probe(input clk,rst,a,b);
ap: assert property (@(posedge clk) disable iff (rst) a |=> b);
endmodule
