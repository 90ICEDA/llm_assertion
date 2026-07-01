module dut_case10 (
    input  wire clk,
    input  wire rst_n,
    input  wire fire,
    input  wire ready_i,
    output reg  valid_o
);
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        valid_o <= 1'b0;
    end else begin
        if (fire) begin
            valid_o <= 1'b1;
        end else if (valid_o && ready_i) begin
            valid_o <= 1'b0;
        end
    end
end
endmodule
