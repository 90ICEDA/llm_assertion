module cc_credit_counter #(parameter integer NumCredits=4, parameter InitCreditEmpty=0)(input clk_i,rst_ni,clr_i,input credit_give_i,credit_take_i,output reg [2:0] credit_o,output credit_left_o,credit_crit_o,credit_full_o);
wire decrement=credit_take_i & ~credit_give_i; wire increment=~credit_take_i & credit_give_i;
always @(posedge clk_i or negedge rst_ni) if(!rst_ni) credit_o<=InitCreditEmpty?0:NumCredits; else if(clr_i) credit_o<=InitCreditEmpty?0:NumCredits; else if(decrement) credit_o<=credit_o-1'b1; else if(increment) credit_o<=credit_o+1'b1;
assign credit_left_o=credit_o!=0; assign credit_crit_o=credit_o==NumCredits-1; assign credit_full_o=credit_o==NumCredits; endmodule
