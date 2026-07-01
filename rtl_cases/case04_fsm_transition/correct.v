module dut_case04 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire       finish,
    output reg  [1:0] state
);
localparam S_IDLE = 2'd0;
localparam S_BUSY = 2'd1;
localparam S_DONE = 2'd2;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= S_IDLE;
    end else begin
        case (state)
            S_IDLE: if (start)  state <= S_BUSY;
            S_BUSY: if (finish) state <= S_DONE;
            S_DONE:             state <= S_IDLE;
            default:            state <= S_IDLE;
        endcase
    end
end
endmodule
