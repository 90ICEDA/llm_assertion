module cc_stream_delay #(parameter Width=8,parameter FixedDelay=3)(input clk_i,rst_ni,clr_i,input [Width-1:0] payload_i,input valid_i,output ready_o,output reg [Width-1:0] payload_o,output reg valid_o,input ready_i); reg [7:0] count; reg busy; assign ready_o=!busy; always @(posedge clk_i or negedge rst_ni) if(!rst_ni) begin count<=0;busy<=0;valid_o<=0;payload_o<=0;end else if(clr_i) begin count<=0;busy<=0;valid_o<=0;end else begin if(valid_o&&ready_i) begin valid_o<=0;busy<=0;end if(valid_i&&ready_o) begin payload_o<=payload_i;
// MUTATION: output becomes valid one cycle early.
count<=FixedDelay-1;
busy<=1;end else if(busy&&!valid_o) begin if(count==1) valid_o<=1; else count<=count-1'b1; end end endmodule
