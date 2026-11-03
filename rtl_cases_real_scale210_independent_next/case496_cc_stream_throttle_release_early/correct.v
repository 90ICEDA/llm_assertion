`timescale 1ns/1ps
module cc_stream_throttle(
  input wire clk_i,
  input wire rst_ni,
  input wire start_i,
  input wire enable_i,
  
  output wire q_o,
  output wire [7:0] state_o
);
  reg [2:0] count;
  reg retry;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin count<=0; retry<=0; end
    else if (enable_i) begin
      retry <= (count == 1);
      if (start_i) count <= 3;
      else if (count != 0) count <= count - 1'b1;
    end
  end
  assign q_o = retry;
  assign state_o = {5'b0,count};
endmodule
