`timescale 1ns/1ps
`default_nettype none
module tb;
reg clk = 1'b0;
always #5 clk = ~clk;
reg rst = 1'b1;
string vcd_file;
initial begin
    if (!$value$plusargs("VCD=%s", vcd_file)) begin
        vcd_file = "wave.vcd";
    end
    $dumpfile(vcd_file);
    $dumpvars(0, tb);
end
reg [7:0] s_data = 8'd0;
reg s_valid = 1'b0;
reg s_last = 1'b0;
reg ll_not_ready = 1'b0;
wire s_ready;
wire [7:0] ll_data;
wire ll_sof_n;
wire ll_eof_n;
wire ll_src_rdy_n;
axis_ll_bridge dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_data), .s_axis_tvalid(s_valid),
    .s_axis_tready(s_ready), .s_axis_tlast(s_last),
    .ll_data_out(ll_data), .ll_sof_out_n(ll_sof_n),
    .ll_eof_out_n(ll_eof_n), .ll_src_rdy_out_n(ll_src_rdy_n),
    .ll_dst_rdy_in_n(ll_not_ready)
);
task axis_beat(input [7:0] data, input last);
begin
    @(negedge clk); s_data = data; s_last = last; s_valid = 1'b1; ll_not_ready = 1'b0;
    @(negedge clk); s_valid = 1'b0;
end
endtask
task stall_beat(input [7:0] data, input last);
begin
    @(negedge clk); s_data = data; s_last = last; s_valid = 1'b1; ll_not_ready = 1'b1;
    repeat (2) @(negedge clk);
    s_valid = 1'b0; ll_not_ready = 1'b0;
end
endtask
initial begin
    repeat (3) @(posedge clk);
    @(negedge clk); rst = 1'b0;
`ifdef STIM_HOLDOUT
axis_beat(8'ha1, 1'b0); stall_beat(8'ha2, 1'b1); repeat (1) @(posedge clk); axis_beat(8'ha3, 1'b0); axis_beat(8'ha4, 1'b1);
`elsif STIM_DECOY
axis_beat(8'hd1, 1'b0); stall_beat(8'hd2, 1'b1); stall_beat(8'hd3, 1'b0); axis_beat(8'hd4, 1'b0); axis_beat(8'hd5, 1'b1);
`else
axis_beat(8'h11, 1'b0); stall_beat(8'h22, 1'b1); axis_beat(8'h23, 1'b0); axis_beat(8'h24, 1'b1);
`endif
    repeat (5) @(posedge clk); $finish;
end
endmodule
`default_nettype wire
