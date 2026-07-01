module dut_case01 (
    input  wire clk,
    input  wire rst_n,
    input  wire en,
    input  wire din,
    output reg  q
);
always @(posedge clk) begin
    // BUG: reset path is missing.
    if (en) begin
        q <= din;
    end
end
endmodule
