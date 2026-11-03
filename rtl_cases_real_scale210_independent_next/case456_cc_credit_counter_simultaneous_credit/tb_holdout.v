`timescale 1ns/1ps
module tb;
  reg clk_i=0,rst_ni=0,clr_i=0; always #5 clk_i=~clk_i;
  reg credit_give_i=0,credit_take_i=0; wire [2:0] q_o; wire [2:0] credit_o=q_o; wire l,c,f;
  cc_credit_counter #(.NumCredits(4)) dut(.clk_i,.rst_ni,.clr_i,.credit_give_i,.credit_take_i,.credit_o(q_o),.credit_left_o(l),.credit_crit_o(c),.credit_full_o(f));
  initial begin $monitor("T=%0t q=%0d give=%b take=%b",$time,q_o,credit_give_i,credit_take_i); #2 rst_ni=0; #10 rst_ni=1; #13 credit_take_i=1;#20 credit_take_i=0;credit_give_i=1;#10 credit_take_i=1;#10 credit_give_i=0;credit_take_i=0; #30 $finish; end
endmodule
