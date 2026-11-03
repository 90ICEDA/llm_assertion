`timescale 1ns/1ps
`default_nettype none
module tb;
 reg clk=0;always #5 clk=~clk;reg rst=1,enable=0,mr=0;reg [1:0] select=0;reg [31:0] sd=0;reg [3:0] sv=0,sl=0;wire [3:0] sr;wire [7:0] md;wire mv,ml;string vcd_file;
 localparam integer DATA_WIDTH = 8;
 wire [31:0] s_axis_tdata=sd; wire [3:0] s_axis_tvalid=sv, s_axis_tready=sr;
 wire [7:0] m_axis_tdata=md; wire m_axis_tvalid=mv, m_axis_tready=mr;
 wire s_axis_tready_selected=sr[select];
 wire [7:0] s_axis_tdata_selected=sd[select*8 +: 8];
 axis_mux #(.S_COUNT(4),.DATA_WIDTH(8),.KEEP_ENABLE(0),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(0)) dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tkeep(4'b1111),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tlast(sl),.s_axis_tid(32'b0),.s_axis_tdest(32'b0),.s_axis_tuser(4'b0),.m_axis_tdata(md),.m_axis_tkeep(),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tlast(ml),.m_axis_tid(),.m_axis_tdest(),.m_axis_tuser(),.enable(enable),.select(select));
 initial begin if(!$value$plusargs("VCD=%s",vcd_file))vcd_file="wave.vcd";$dumpfile(vcd_file);$dumpvars(0,tb);
`ifdef STIM_HOLDOUT
 repeat(3) @(posedge clk);#1 rst=0;enable=1;select=2;mr=0;sd[23:16]=8'hb2;sv=4'b0100;
`elsif STIM_DECOY
 repeat(4) @(posedge clk);#1 rst=0;enable=1;select=3;mr=0;sd[31:24]=8'hd4;sv=4'b1000;
`else
 repeat(2) @(posedge clk);#1 rst=0;enable=1;select=1;mr=0;sd[15:8]=8'ha1;sv=4'b0010;
`endif
 @(posedge clk);#1 mr=1;repeat(2) @(posedge clk);#1 sv=0;repeat(4) @(posedge clk);$finish;end
endmodule
`default_nettype wire
