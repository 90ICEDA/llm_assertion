module dut_case09 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       step,
    output reg  [7:0] addr
);
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        addr <= 8'h00;
    end else if (step) begin
        addr <= addr + 8'd4;
    end
end
endmodule
