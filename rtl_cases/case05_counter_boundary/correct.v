module dut_case05 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       en,
    input  wire [2:0] limit,
    output reg  [2:0] cnt
);
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        cnt <= 3'd0;
    end else if (en) begin
        if (cnt == limit) cnt <= 3'd0;
        else              cnt <= cnt + 3'd1;
    end
end
endmodule
