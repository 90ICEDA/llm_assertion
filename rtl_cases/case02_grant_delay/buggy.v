module dut_case02 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [1:0] req,
    output reg  [1:0] grant
);
reg [1:0] req_d;
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        req_d <= 2'b00;
        grant <= 2'b00;
    end else begin
        req_d <= req;
        // BUG: grant is delayed by one cycle.
        grant <= req_d;
    end
end
endmodule
