`timescale 1ns/1ps
// OpenTitan prim_subreg W1C arbitration extraction.
module prim_subreg #(
  parameter integer DW=8, parameter [DW-1:0] RESVAL=0
)(
  input wire clk_i,rst_ni,we,de,
  input wire [DW-1:0] wd,d,
  output wire qe,
  output reg [DW-1:0] q,
  output wire [DW-1:0] ds,qs
);
  wire wr_en=we|de;
  // MUTATION: HW replacement is given whole-register priority over simultaneous W1C.
  wire [DW-1:0] wr_data=de?d:(we?(q&~wd):q);
  always @(posedge clk_i or negedge rst_ni)
    if(!rst_ni) q<=RESVAL; else if(wr_en) q<=wr_data;
  assign ds=wr_en?wr_data:q;
  assign qs=q;
  assign qe=we;
endmodule
