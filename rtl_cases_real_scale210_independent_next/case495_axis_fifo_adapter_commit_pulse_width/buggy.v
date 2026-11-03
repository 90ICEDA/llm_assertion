`timescale 1ns/1ps
module axis_fifo_adapter(
  input wire clk_i,
  input wire rst_ni,
  input wire delimiter_i,
  input wire output_ready_i,
  
  output wire q_o,
  output wire [7:0] state_o
);
  reg valid_reg;
  reg hold_reg;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin valid_reg<=0; hold_reg<=0; end
    else if (output_ready_i) begin
      valid_reg <= delimiter_i | hold_reg;
      hold_reg <= delimiter_i;
    end
  end
  assign q_o = valid_reg;
  assign state_o = {6'b0,hold_reg,valid_reg};
endmodule
