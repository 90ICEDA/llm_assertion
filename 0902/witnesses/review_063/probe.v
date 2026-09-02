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
reg [7:0] s_data = 8'd101;
reg s_valid = 1'b0;
reg m_ready = 1'b0;
wire s_ready;
wire [7:0] m_data;
wire m_valid;
axis_srl_register #(.DATA_WIDTH(8), .KEEP_ENABLE(0), .LAST_ENABLE(0), .ID_ENABLE(0), .DEST_ENABLE(0), .USER_ENABLE(0)) dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_data), .s_axis_tkeep(1'b1), .s_axis_tvalid(s_valid), .s_axis_tready(s_ready),
    .s_axis_tlast(1'b0), .s_axis_tid(8'b0), .s_axis_tdest(8'b0), .s_axis_tuser(1'b0),
    .m_axis_tdata(m_data), .m_axis_tkeep(), .m_axis_tvalid(m_valid), .m_axis_tready(m_ready),
    .m_axis_tlast(), .m_axis_tid(), .m_axis_tdest(), .m_axis_tuser()
);
task push(input [7:0] data);
begin
    @(negedge clk); s_data = data; s_valid = 1'b1;
    @(negedge clk); s_valid = 1'b0;
end
endtask
initial begin
    repeat (3) @(posedge clk); @(negedge clk); rst = 1'b0; m_ready = 1'b1;
`ifdef STIM_HOLDOUT
push(8'hb1); @(negedge clk); m_ready = 1'b0; repeat (2) @(posedge clk); @(negedge clk); m_ready = 1'b1; repeat (3) @(posedge clk);
`elsif STIM_DECOY
push(8'he1); @(negedge clk); m_ready = 1'b0; @(posedge clk); @(negedge clk); m_ready = 1'b1; s_data = 8'haa; s_valid = 1'b1; @(negedge clk); s_valid = 1'b0;
`else
push(8'h31); @(negedge clk); m_ready = 1'b0; @(posedge clk); @(negedge clk); m_ready = 1'b1; repeat (3) @(posedge clk);
`endif
    repeat (5) @(posedge clk); repeat (1) @(posedge clk); $finish;
end
endmodule
`default_nettype wire
