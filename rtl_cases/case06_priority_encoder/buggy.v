module dut_case06 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [3:0] req,
    output reg  [3:0] grant
);
reg [3:0] grant_nxt;

always @(*) begin
    // BUG: priority is reversed (lowest bit wins).
    if      (req[0]) grant_nxt = 4'b0001;
    else if (req[1]) grant_nxt = 4'b0010;
    else if (req[2]) grant_nxt = 4'b0100;
    else if (req[3]) grant_nxt = 4'b1000;
    else             grant_nxt = 4'b0000;
end

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) grant <= 4'b0000;
    else        grant <= grant_nxt;
end
endmodule
