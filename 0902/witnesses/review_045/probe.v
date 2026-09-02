`timescale 1ns/1ps
`default_nettype none
module tb; reg clk=0; always #5 clk=~clk; reg rst=1; string vcd_file;
initial begin if(!$value$plusargs("VCD=%s",vcd_file))vcd_file="wave.vcd";$dumpfile(vcd_file);$dumpvars(0,tb);end
reg[7:0]sd=0;reg sv=0,sl=0,mr=1;wire sr,mv,ml;wire[31:0]md;
axis_adapter #(.S_DATA_WIDTH(8),.S_KEEP_ENABLE(0),.M_DATA_WIDTH(32),.M_KEEP_ENABLE(1),.USER_ENABLE(0)) dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tkeep(1'b1),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tlast(sl),.s_axis_tid(8'b0),.s_axis_tdest(8'b0),.s_axis_tuser(1'b0),.m_axis_tdata(md),.m_axis_tkeep(),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tlast(ml),.m_axis_tid(),.m_axis_tdest(),.m_axis_tuser());
task send(input[7:0]d,input l);begin @(negedge clk);sd=d;sl=l;sv=1;while(!sr)@(negedge clk);@(negedge clk);sv=0;end endtask
initial begin repeat(3)@(posedge clk);@(negedge clk);rst=0;`ifdef STIM_HOLDOUT
send(8'ha1,0);@(negedge clk);send(8'ha2,0);send(8'ha3,0);send(8'ha4,1);
`elsif STIM_DECOY
send(8'hd1,0);send(8'hd2,0);mr=0;send(8'hd3,0);@(negedge clk);mr=1;send(8'hd4,1);
`else
send(8'h11,0);send(8'h22,0);send(8'h33,0);send(8'h44,1);
`endif repeat(8)@(posedge clk);repeat (1) @(posedge clk); $finish;end
endmodule
`default_nettype wire
