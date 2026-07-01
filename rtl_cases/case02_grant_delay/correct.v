module dut_case02 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [1:0] req,
    output reg  [1:0] grant
);
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        grant <= 2'b00;
    end else begin
        grant <= req;
    end
end
endmodule
