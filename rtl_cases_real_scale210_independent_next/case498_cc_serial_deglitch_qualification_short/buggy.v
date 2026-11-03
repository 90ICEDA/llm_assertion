`timescale 1ns/1ps
module cc_serial_deglitch(
  input wire clk_i,
  input wire rst_ni,
  input wire noisy_i,
  input wire sample_enable_i,
  
  output wire q_o,
  output wire [7:0] state_o
);
  reg [1:0] high_count;
  reg filtered;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin high_count<=0; filtered<=0; end
    else if (sample_enable_i) begin
      if (!noisy_i) begin high_count<=0; filtered<=0; end
      else begin
        if (high_count != 3) high_count <= high_count + 1'b1;
        if (high_count >= 1) filtered <= 1'b1;
      end
    end
  end
  assign q_o = filtered;
  assign state_o = {6'b0,high_count};
endmodule
