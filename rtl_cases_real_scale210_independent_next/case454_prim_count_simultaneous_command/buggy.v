`timescale 1ns/1ps
module prim_count #(parameter integer Width=4)(input logic clk_i,rst_ni,clr_i,set_i,incr_en_i,decr_en_i,
 input logic [Width-1:0] set_cnt_i,step_i,input logic commit_i,
 output logic [Width-1:0] cnt_o,cnt_after_commit_o,output logic err_o);
 logic [Width-1:0] cnt_q,cnt_d,cnt_d_committed; logic [Width:0] ext_cnt; logic uflow,oflow,cnt_en;
 assign ext_cnt=decr_en_i?{1'b0,cnt_q}-{1'b0,step_i}:incr_en_i?{1'b0,cnt_q}+{1'b0,step_i}:{1'b0,cnt_q};
 assign oflow=incr_en_i&&ext_cnt[Width]; assign uflow=decr_en_i&&ext_cnt[Width];
 wire [Width-1:0] cnt_sat=uflow?'0:oflow?{Width{1'b1}}:ext_cnt[Width-1:0];
 assign cnt_en=(incr_en_i | decr_en_i)&&((incr_en_i&&!(&cnt_q))||(decr_en_i&&cnt_q!='0));
 assign cnt_d=clr_i?'0:set_i?set_cnt_i:cnt_en?cnt_sat:cnt_q;
 assign cnt_d_committed = commit_i ? cnt_d : cnt_q;
 always_ff @(posedge clk_i or negedge rst_ni) if(!rst_ni) cnt_q<='0; else cnt_q<=cnt_d_committed;
 assign cnt_o=cnt_q; assign cnt_after_commit_o=cnt_d; assign err_o=0;
endmodule
