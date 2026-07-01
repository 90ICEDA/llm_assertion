module dut_case03 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       valid_i,
    input  wire       ready_i,
    input  wire [7:0] data_i,
    output reg        valid_o,
    output reg  [7:0] data_o
);
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        valid_o <= 1'b0;
        data_o <= 8'h00;
    end else if (valid_i || ready_i) begin
        // BUG: should require valid_i && ready_i.
        valid_o <= 1'b1;
        data_o <= data_i;
    end else begin
        valid_o <= 1'b0;
    end
end
endmodule
