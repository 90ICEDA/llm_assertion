`timescale 1ns/1ps
`default_nettype none
module tb; reg clk=0; always #5 clk=~clk; reg rst=1; string vcd_file;
initial begin if(!$value$plusargs("VCD=%s",vcd_file))vcd_file="wave.vcd";$dumpfile(vcd_file);$dumpvars(0,tb);end
reg[7:0]sd=0;reg sv=0,sl=0,mr=1;wire sr,mv,ml,status_valid,status_pad,status_trunc;wire[7:0]md;wire[15:0]status_len,status_orig;
axis_frame_length_adjust #(.DATA_WIDTH(8),.KEEP_ENABLE(0),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(0))dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tkeep(1'b1),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tlast(sl),.s_axis_tid(8'b0),.s_axis_tdest(8'b0),.s_axis_tuser(1'b0),.m_axis_tdata(md),.m_axis_tkeep(),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tlast(ml),.m_axis_tid(),.m_axis_tdest(),.m_axis_tuser(),.status_valid(status_valid),.status_ready(1'b1),.status_frame_pad(status_pad),.status_frame_truncate(status_trunc),.status_frame_length(status_len),.status_frame_original_length(status_orig),.length_min(16'd1),.length_max(16'd4));
task send(input[7:0]d,input l);begin @(negedge clk);sd=d;sl=l;sv=1;while(!sr)@(negedge clk);@(negedge clk);sv=0;end endtask
initial begin repeat(3)@(posedge clk);@(negedge clk);rst=0;`ifdef STIM_HOLDOUT
send(8'hc1,0);@(negedge clk);send(8'hc2,0);send(8'hc3,0);send(8'hc4,0);send(8'hc5,1);
`elsif STIM_DECOY
send(8'he1,0);send(8'he2,0);mr=0;send(8'he3,0);@(negedge clk);mr=1;send(8'he4,0);send(8'he5,1);
`else
send(8'h41,0);send(8'h42,0);send(8'h43,0);send(8'h44,0);send(8'h45,1);
`endif repeat(12)@(posedge clk);$finish;end
endmodule
`default_nettype wire
