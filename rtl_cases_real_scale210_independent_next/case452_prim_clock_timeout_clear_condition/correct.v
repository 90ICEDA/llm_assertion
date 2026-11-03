`timescale 1ns/1ps
module prim_clock_timeout #(parameter integer TimeOutCnt=4, parameter integer CntWidth=3)(
 input logic clk_chk_i,rst_chk_ni,clk_i,rst_ni,en_i, output logic timeout_o);
 logic [CntWidth-1:0] cnt; logic ack,timeout; logic chk_seen;
 always_ff @(posedge clk_chk_i or negedge rst_chk_ni) begin
   if(!rst_chk_ni) chk_seen<=0; else chk_seen<=~chk_seen;
 end
 logic chk_q1,chk_q2;
 always_ff @(posedge clk_i or negedge rst_ni) begin
   if(!rst_ni) begin chk_q1<=0; chk_q2<=0; end else begin chk_q1<=chk_seen; chk_q2<=chk_q1; end
 end
 assign ack=chk_q1^chk_q2;
 assign timeout = int'(cnt) >= TimeOutCnt;
 always_ff @(posedge clk_i or negedge rst_ni) begin
   if(!rst_ni) cnt<='0;
   else if(ack || !en_i) cnt<='0;
   else if(timeout) cnt<={CntWidth{1'b1}};
   else if(en_i) cnt<=cnt+1'b1;
 end
 always_ff @(posedge clk_i or negedge rst_ni) if(!rst_ni) timeout_o<=0; else timeout_o<=timeout;
endmodule
