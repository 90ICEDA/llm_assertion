`timescale 1ns/1ps
`default_nettype none
module tb;
 reg clk=0; always #5 clk=~clk; reg rst=1, sv=0, sl=0, mr=1, by_frame=0; reg [7:0] sd=0; wire sr,mv,ml; wire [7:0] md; string vcd_file;
 wire s_axis_tvalid=sv, s_axis_tready=sr, s_axis_tlast=sl;
 wire m_axis_tvalid=mv, m_axis_tready=mr, m_axis_tlast=ml;
 wire [7:0] s_axis_tdata=sd, m_axis_tdata=md;
 axis_rate_limit #(.DATA_WIDTH(8),.KEEP_ENABLE(0),.LAST_ENABLE(1),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(0)) dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tkeep(1'b1),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tlast(sl),.s_axis_tid(8'b0),.s_axis_tdest(8'b0),.s_axis_tuser(1'b0),.m_axis_tdata(md),.m_axis_tkeep(),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tlast(ml),.m_axis_tid(),.m_axis_tdest(),.m_axis_tuser(),.rate_num(8'd1),.rate_denom(8'd3),.rate_by_frame(by_frame));
 task automatic send_beat(input [7:0] data, input last);
   begin
     sd=data; sl=last; sv=1;
     do @(posedge clk); while(!sr);
     #1 sv=0; sl=0;
   end
 endtask
 initial begin if(!$value$plusargs("VCD=%s",vcd_file)) vcd_file="wave.vcd"; $dumpfile(vcd_file);$dumpvars(0,tb);
`ifdef STIM_HOLDOUT
 repeat(3) @(posedge clk);#1 rst=0;
`ifdef RATE_LIMIT_PER_BEAT
 by_frame=0;
`else
 by_frame=1;
`endif
 send_beat(8'hb0,0); repeat(2) @(posedge clk); send_beat(8'hb1,0); send_beat(8'hb2,1);
`elsif STIM_DECOY
 repeat(4) @(posedge clk);#1 rst=0;
`ifdef RATE_LIMIT_PER_BEAT
 by_frame=0;
`else
 by_frame=1;
`endif
 send_beat(8'hd0,0); repeat(3) @(posedge clk); send_beat(8'hd1,0); send_beat(8'hd2,1);
`else
 repeat(2) @(posedge clk);#1 rst=0;
`ifdef RATE_LIMIT_PER_BEAT
 by_frame=0;
`else
 by_frame=1;
`endif
 send_beat(8'ha0,0); repeat(1) @(posedge clk); send_beat(8'ha1,0); send_beat(8'ha2,1);
`endif
 repeat(8) @(posedge clk);$finish; end
endmodule
`default_nettype wire
