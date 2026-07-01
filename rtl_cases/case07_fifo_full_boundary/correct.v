module dut_case07 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       wr_en,
    input  wire       rd_en,
    output reg  [2:0] count,
    output wire       full,
    output wire       empty
);
assign full  = (count == 3'd4);
assign empty = (count == 3'd0);

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        count <= 3'd0;
    end else begin
        case ({wr_en, rd_en})
            2'b10: if (!full)  count <= count + 3'd1;
            2'b01: if (!empty) count <= count - 3'd1;
            default:           count <= count;
        endcase
    end
end
endmodule
