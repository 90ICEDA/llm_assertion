`timescale 1ns/1ps
`default_nettype none
module tb;
  reg clk=0; always #5 clk=~clk;
  reg rst=1, s_axis_tvalid=0, s_axis_tlast=0, m_axis_tready=0;
  reg [7:0] s_axis_tdata=0;
  wire s_axis_tready, m_axis_tvalid, m_axis_tlast; wire [7:0] m_axis_tdata;
  string vcd_file;
  axis_register #(.DATA_WIDTH(8),.KEEP_ENABLE(0),.LAST_ENABLE(1),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(0),.REG_TYPE(2)) dut(
    .clk(clk),.rst(rst),.s_axis_tdata(s_axis_tdata),.s_axis_tkeep(1'b1),.s_axis_tvalid(s_axis_tvalid),.s_axis_tready(s_axis_tready),.s_axis_tlast(s_axis_tlast),.s_axis_tid(8'b0),.s_axis_tdest(8'b0),.s_axis_tuser(1'b0),
    .m_axis_tdata(m_axis_tdata),.m_axis_tkeep(),.m_axis_tvalid(m_axis_tvalid),.m_axis_tready(m_axis_tready),.m_axis_tlast(m_axis_tlast),.m_axis_tid(),.m_axis_tdest(),.m_axis_tuser());
  initial begin
    if(!$value$plusargs("VCD=%s",vcd_file)) vcd_file="wave.vcd"; $dumpfile(vcd_file); $dumpvars(0,tb);
`ifdef STIM_HOLDOUT
    repeat(3) @(posedge clk); #1 rst=0; m_axis_tready=1;
    @(posedge clk); #1 s_axis_tdata=8'hb6; s_axis_tvalid=1; s_axis_tlast=0;
    @(posedge clk); #1 m_axis_tready=0; s_axis_tdata=8'hc7; s_axis_tlast=1;
    @(posedge clk); #1 s_axis_tvalid=0;
    repeat(2) @(posedge clk); #1 m_axis_tready=1;
`elsif STIM_DECOY
    repeat(4) @(posedge clk); #1 rst=0; m_axis_tready=1;
    @(posedge clk); #1 s_axis_tdata=8'h39; s_axis_tvalid=1;
    @(posedge clk); #1 m_axis_tready=0; s_axis_tdata=8'h4a;
    @(posedge clk); #1 s_axis_tvalid=0;
    repeat(3) @(posedge clk); #1 m_axis_tready=1;
`else
    repeat(2) @(posedge clk); #1 rst=0; m_axis_tready=1;
    @(posedge clk); #1 s_axis_tdata=8'ha5; s_axis_tvalid=1;
    @(posedge clk); #1 m_axis_tready=0; s_axis_tdata=8'h5a;
    @(posedge clk); #1 s_axis_tvalid=0;
    repeat(2) @(posedge clk); #1 m_axis_tready=1;
`endif
    @(posedge clk); #1 s_axis_tvalid=0; s_axis_tlast=0;
    repeat(6) @(posedge clk); $finish;
  end
endmodule
`default_nettype wire
