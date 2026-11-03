`timescale 1ns/1ps
`default_nettype none
module tb; reg clk=0; always #5 clk=~clk; reg rst=1; string vcd_file;
initial begin if(!$value$plusargs("VCD=%s",vcd_file))vcd_file="wave.vcd";$dumpfile(vcd_file);$dumpvars(0,tb);end
reg[7:0]sd=0;reg sv=0,mr=0;wire sr,mv;wire[7:0]md;wire[2:0]count;
axis_srl_fifo #(.DATA_WIDTH(8),.KEEP_ENABLE(0),.LAST_ENABLE(0),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(0),.DEPTH(4))dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tkeep(1'b1),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tlast(1'b0),.s_axis_tid(8'b0),.s_axis_tdest(8'b0),.s_axis_tuser(1'b0),.m_axis_tdata(md),.m_axis_tkeep(),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tlast(),.m_axis_tid(),.m_axis_tdest(),.m_axis_tuser(),.count(count));
task push(input[7:0]d);begin @(negedge clk);sd=d;sv=1;while(!sr)@(negedge clk);@(negedge clk);sv=0;end endtask
initial begin repeat(3)@(posedge clk);@(negedge clk);rst=0;`ifdef STIM_HOLDOUT
push(8'hd1);push(8'hd2);push(8'hd3);@(negedge clk);mr=1;sd=8'hd4;sv=1;@(negedge clk);sv=0;
`elsif STIM_DECOY
push(8'hf1);@(negedge clk);mr=1;sd=8'hf2;sv=1;@(negedge clk);sv=0;
`else
push(8'h51);push(8'h52);@(negedge clk);mr=1;sd=8'h53;sv=1;@(negedge clk);sv=0;
`endif repeat(8)@(posedge clk);$finish;end
endmodule
`default_nettype wire
