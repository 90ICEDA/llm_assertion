module dut_case01 (
    input  wire clk,
    input  wire rst_n,
    input  wire en,
    input  wire din,
    output reg  q
);
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        q <= 1'b0;
    end else if (en) begin
        q <= din;
    end
end
endmodule
