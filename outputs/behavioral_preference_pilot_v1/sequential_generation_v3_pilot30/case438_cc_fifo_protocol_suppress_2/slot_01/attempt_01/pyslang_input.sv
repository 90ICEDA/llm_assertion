module v3_native;
logic clk_i;
logic rst_ni;
logic clr_i;
logic flush_i;
logic full_o;
logic empty_o;
logic push_i;
logic pop_i;
logic usage_o;
logic data_i;
logic data_o;
V3: assert property (@(posedge clk_i) disable iff (!rst_ni) (push_i) |-> (empty_o));
endmodule
