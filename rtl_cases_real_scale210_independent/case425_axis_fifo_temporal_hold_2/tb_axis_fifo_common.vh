`timescale 1ns/1ps
`default_nettype none
module tb;
  reg clk = 0; always #5 clk = ~clk;
  reg rst = 1;
  reg [7:0] s_axis_tdata = 0;
  reg s_axis_tvalid = 0, s_axis_tlast = 0, s_axis_tuser = 0;
  wire s_axis_tready;
  wire [7:0] m_axis_tdata; wire m_axis_tvalid, m_axis_tlast;
  wire status_bad_frame, status_good_frame, status_overflow;
  string vcd_file;
  axis_fifo #(.DEPTH(8), .DATA_WIDTH(8), .KEEP_ENABLE(0), .LAST_ENABLE(1),
    .ID_ENABLE(0), .DEST_ENABLE(0), .USER_ENABLE(1), .USER_WIDTH(1),
    .FRAME_FIFO(1), .DROP_OVERSIZE_FRAME(1), .DROP_BAD_FRAME(1)) dut (
    .clk(clk), .rst(rst), .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(1'b1),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready), .s_axis_tlast(s_axis_tlast),
    .s_axis_tid(8'b0), .s_axis_tdest(8'b0), .s_axis_tuser(s_axis_tuser),
    .m_axis_tdata(m_axis_tdata), .m_axis_tkeep(), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(1'b1), .m_axis_tlast(m_axis_tlast), .m_axis_tid(), .m_axis_tdest(),
    .m_axis_tuser(), .pause_req(1'b0), .pause_ack(), .status_depth(),
    .status_depth_commit(), .status_overflow(status_overflow),
    .status_bad_frame(status_bad_frame), .status_good_frame(status_good_frame));
  initial begin
    if (!$value$plusargs("VCD=%s", vcd_file)) vcd_file = "wave.vcd";
    $dumpfile(vcd_file); $dumpvars(0, tb);
`ifdef STIM_HOLDOUT
    repeat (3) @(posedge clk); #1 rst=0;
    repeat (2) @(posedge clk); #1;
    s_axis_tdata=8'hd2; s_axis_tuser=1; s_axis_tlast=1; s_axis_tvalid=1;
`elsif STIM_DECOY
    repeat (4) @(posedge clk); #1 rst=0;
    @(posedge clk); #1 s_axis_tdata=8'h63; s_axis_tuser=0; s_axis_tlast=0; s_axis_tvalid=1;
    @(posedge clk); #1 s_axis_tdata=8'h64; s_axis_tuser=1; s_axis_tlast=1;
`else
    repeat (2) @(posedge clk); #1 rst=0;
    @(posedge clk); #1 s_axis_tdata=8'hc1; s_axis_tuser=1; s_axis_tlast=1; s_axis_tvalid=1;
`endif
    @(posedge clk); #1 s_axis_tvalid=0; s_axis_tlast=0; s_axis_tuser=0;
    repeat (5) @(posedge clk); $finish;
  end
endmodule
`default_nettype wire
