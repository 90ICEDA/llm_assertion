`timescale 1ns/1ps
// Flattened Icarus-friendly extraction of OpenTitan prim_racl_error_arb (N=4).
module prim_racl_error_arb(
  input wire clk_i,rst_ni,
  input wire [3:0] error_valid_i,error_overflow_i,
  input wire [31:0] error_payload_i,
  output reg error_valid_o,error_overflow_o,
  output reg [7:0] error_payload_o
);
  reg [3:0] gnt;
  always @* begin
    gnt=4'b0000; error_valid_o=1'b0; error_payload_o=8'h00;
    if(error_valid_i[0]) begin gnt=4'b0001; error_valid_o=1; error_payload_o=error_payload_i[7:0]; end
    else if(error_valid_i[1]) begin gnt=4'b0010; error_valid_o=1; error_payload_o=error_payload_i[15:8]; end
    else if(error_valid_i[2]) begin gnt=4'b0100; error_valid_o=1; error_payload_o=error_payload_i[23:16]; end
    else if(error_valid_i[3]) begin gnt=4'b1000; error_valid_o=1; error_payload_o=error_payload_i[31:24]; end
    error_overflow_o=|(error_valid_i&error_overflow_i) |
                     (error_valid_o & |(error_valid_i&~gnt));
  end
  wire unused=clk_i^rst_ni;
endmodule
