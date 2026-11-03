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
reg [7:0] ll_data = 8'h55;
reg ll_sof_n = 1'b0;
reg ll_eof_n = 1'b1;
reg ll_src_rdy_n = 1'b0;
reg m_ready = 1'b0;
wire ll_dst_rdy_n;
wire [7:0] m_data;
wire m_valid;
wire m_last;
ll_axis_bridge dut (
    .clk(clk), .rst(rst),
    .ll_data_in(ll_data), .ll_sof_in_n(ll_sof_n), .ll_eof_in_n(ll_eof_n),
    .ll_src_rdy_in_n(ll_src_rdy_n), .ll_dst_rdy_out_n(ll_dst_rdy_n),
    .m_axis_tdata(m_data), .m_axis_tvalid(m_valid), .m_axis_tready(m_ready), .m_axis_tlast(m_last)
);
initial begin
    repeat (3) @(posedge clk); @(negedge clk); rst = 1'b0;
`ifdef STIM_HOLDOUT
m_ready = 1'b0; repeat (2) @(posedge clk); @(negedge clk); m_ready = 1'b1;
`elsif STIM_DECOY
m_ready = 1'b1; @(negedge clk); m_ready = 1'b0; @(negedge clk); m_ready = 1'b1;
`else
m_ready = 1'b1; repeat (2) @(posedge clk); @(negedge clk); m_ready = 1'b0;
`endif
    repeat (3) @(posedge clk); $finish;
end
endmodule
`default_nettype wire
