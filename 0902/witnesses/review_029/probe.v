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
reg s_last = 1'b0;
reg m_ready = 1'b1;
wire s_ready;
wire [7:0] m_data;
wire m_valid;
wire m_last;
wire m_user;
integer j;
axis_cobs_decode dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_data), .s_axis_tvalid(s_valid), .s_axis_tready(s_ready),
    .s_axis_tlast(s_last), .s_axis_tuser(1'b0),
    .m_axis_tdata(m_data), .m_axis_tvalid(m_valid), .m_axis_tready(m_ready),
    .m_axis_tlast(m_last), .m_axis_tuser(m_user)
);
task send(input [7:0] data, input last);
begin
    @(negedge clk); s_data = data; s_last = last; s_valid = 1'b1;
    while (!s_ready) @(negedge clk);
    @(negedge clk); s_valid = 1'b0;
end
endtask
initial begin
    repeat (3) @(posedge clk); @(negedge clk); rst = 1'b0;
`ifdef STIM_HOLDOUT
send(8'd255, 1'b0);
for (j = 0; j < 254; j = j + 1) send(8'h21 + (j % 13), 1'b0);
send(8'd1, 1'b1);
`elsif STIM_DECOY
send(8'd255, 1'b0);
for (j = 0; j < 254; j = j + 1) begin
    if (j == 97) begin m_ready = 1'b0; repeat (2) @(posedge clk); m_ready = 1'b1; end
    send(8'h31 + (j % 11), 1'b0);
end
send(8'd1, 1'b1);
`else
send(8'd255, 1'b0);
for (j = 0; j < 254; j = j + 1) send(8'h11 + (j % 7), 1'b0);
send(8'd1, 1'b1);
`endif
    repeat (10) @(posedge clk); repeat (1) @(posedge clk); $finish;
end
endmodule
`default_nettype wire
