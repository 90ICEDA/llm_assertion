`timescale 1ns/1ps
`default_nettype none
module tb; reg clk=0; always #5 clk=~clk; reg rst=1; string vcd_file;
initial begin if(!$value$plusargs("VCD=%s",vcd_file))vcd_file="wave.vcd";$dumpfile(vcd_file);$dumpvars(0,tb);end
reg[23:0]sd=0;reg[2:0]sv=0,sl=0;wire[2:0]sr;reg mr=1;wire[7:0]md;wire mv,ml,busy;
// TAG_WIDTH=16 keeps the internal tag-word pointer at a nonzero width for
// Icarus.  TAG_ENABLE remains zero so tag beats do not alter the port stimulus.
axis_frame_join #(.S_COUNT(3),.DATA_WIDTH(8),.TAG_ENABLE(0),.TAG_WIDTH(16))dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tlast(sl),.s_axis_tuser(3'b0),.m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tlast(ml),.m_axis_tuser(),.tag(16'h0),.busy(busy));
// Retire each source only on an actual rising-edge AXIS handshake.  Sampling
// ready on the falling edge clears valid half a cycle before the transfer.
always @(posedge clk) if (!rst) begin sv <= sv & ~sr; sl <= sl & ~sr; end
initial begin repeat(3)@(posedge clk);@(negedge clk);rst=0;`ifdef STIM_HOLDOUT
sd=24'hb3b2b1;sv=3'b111;sl=3'b111;@(negedge clk);
`elsif STIM_DECOY
sd=24'he3e2e1;sv=3'b111;sl=3'b111;mr=0;repeat(2)@(negedge clk);mr=1;
`else
sd=24'h333231;sv=3'b111;sl=3'b111;
`endif repeat(10)@(posedge clk);$finish;end
endmodule
`default_nettype wire
