// Simulation-only behavioral tech-cell models for cc_clk_mux_glitch_free harnesses.
`ifdef CC_CLK_MUX_TB_DEPS
module cc_rstgen(input logic clk_i,rst_ni,test_mode_i,output logic rst_no,init_no);
  logic [1:0] q;
  always @(posedge clk_i or negedge rst_ni) if(!rst_ni) q<=0; else q<={q[0],1'b1};
  assign rst_no=q[1]; assign init_no=q[1];
endmodule
module tc_sync #(parameter integer Stages=2)(input logic clk_i,rst_ni,serial_i,output logic serial_o);
  logic [Stages-1:0] q;
  always @(posedge clk_i or negedge rst_ni) if(!rst_ni) q<='0; else q<={q[Stages-2:0],serial_i};
  assign serial_o=q[Stages-1];
endmodule
module tc_clk_gating #(parameter bit IS_FUNCTIONAL=1)(input logic clk_i,en_i,test_en_i,output logic clk_o);assign clk_o=clk_i&(en_i|test_en_i);endmodule
module tc_clk_or2(input logic clk0_i,clk1_i,output logic clk_o);assign clk_o=clk0_i|clk1_i;endmodule
module tc_clk_xor2(input logic clk0_i,clk1_i,output logic clk_o);assign clk_o=clk0_i^clk1_i;endmodule
module tc_clk_mux2(input logic clk0_i,clk1_i,clk_sel_i,output logic clk_o);assign clk_o=clk_sel_i?clk1_i:clk0_i;endmodule
`endif
