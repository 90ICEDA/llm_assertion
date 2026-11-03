module cc_max_counter #(parameter W=4)(input clk_i,input rst_ni,input clr_i,input clr_max_i,input en_i,input down_i,input [W-1:0] delta_i,output reg [W-1:0] q_o,output [W-1:0] max_o);
  reg [W-1:0] max_q;
  wire [W-1:0] q_next = down_i ? q_o-delta_i : q_o+delta_i;
  assign max_o = max_q;
  always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin q_o<=0;max_q<=0;end
    else if(clr_i) begin q_o<=0;max_q<=0;end
    else begin
      if(clr_max_i) max_q<=0;
      else if(en_i && !down_i && q_o>max_q) max_q<=q_o;
      // MUTATION: peak capture uses the previous count and is one cycle late.
      if(en_i) q_o<=q_next;
    end
  end
endmodule
