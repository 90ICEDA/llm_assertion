`timescale 1ns/1ps
`default_nettype none
module tb; reg clk=0; always #5 clk=~clk; reg rst=1; string vcd_file;
initial begin if(!$value$plusargs("VCD=%s",vcd_file))vcd_file="wave.vcd";$dumpfile(vcd_file);$dumpvars(0,tb);end
reg[7:0]sd=0;reg sv=0;reg[3:0]mr=4'b1111;wire sr;wire[3:0]mv;wire[31:0]md;
axis_broadcast #(.M_COUNT(4),.DATA_WIDTH(8),.KEEP_ENABLE(0),.LAST_ENABLE(0),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(0)) dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tkeep(1'b1),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tlast(1'b0),.s_axis_tid(8'b0),.s_axis_tdest(8'b0),.s_axis_tuser(1'b0),.m_axis_tdata(md),.m_axis_tkeep(),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tlast(),.m_axis_tid(),.m_axis_tdest(),.m_axis_tuser());
task send(input[7:0]d);begin @(negedge clk);sd=d;sv=1;while(!sr)@(negedge clk);@(negedge clk);sv=0;end endtask
initial begin repeat(3)@(posedge clk);@(negedge clk);rst=0;repeat(2)@(posedge clk);`ifdef STIM_HOLDOUT
mr=4'b0101;send(8'hb1);repeat(2)@(negedge clk);mr=4'b1111;
`elsif STIM_DECOY
mr=4'b0010;send(8'he1);repeat(3)@(negedge clk);mr=4'b1111;
`else
mr=4'b0001;send(8'h21);repeat(2)@(negedge clk);mr=4'b1111;
`endif repeat(8)@(posedge clk);$finish;end
endmodule
`default_nettype wire
