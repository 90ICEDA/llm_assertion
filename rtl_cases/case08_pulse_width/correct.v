module dut_case08 (
    input  wire clk,
    input  wire rst_n,
    input  wire trigger,
    output reg  pulse
);
reg [1:0] cnt;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        cnt <= 2'd0;
        pulse <= 1'b0;
    end else begin
        if (trigger) begin
            cnt <= 2'd1;
        end else if (cnt != 2'd0) begin
            cnt <= cnt - 2'd1;
        end
        // Pulse should stay high for 2 cycles including trigger cycle.
        pulse <= trigger || (cnt != 2'd0);
    end
end
endmodule
