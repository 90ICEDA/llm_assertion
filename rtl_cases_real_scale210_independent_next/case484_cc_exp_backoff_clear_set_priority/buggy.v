module cc_exp_backoff(input clk_i,input rst_ni,input clr_i,input set_cnt_i,input clr_cnt_i,output is_zero_o,output [3:0] count_o);
  reg [3:0] count_q;
  reg [3:0] mask_q;
  assign count_o = count_q;
  assign is_zero_o = count_q==0;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin count_q<=0; mask_q<=1; end
    else if (clr_i) begin count_q<=0; mask_q<=1; end
    else if (set_cnt_i) begin count_q<=mask_q; mask_q<={mask_q[2:0],1'b1}; end
    else if (clr_cnt_i) begin count_q<=0; mask_q<=1; end
    else if (1'b0) begin count_q<=mask_q; mask_q<={mask_q[2:0],1'b1}; end
    else if (count_q!=0) count_q<=count_q-1'b1;
  end
endmodule
