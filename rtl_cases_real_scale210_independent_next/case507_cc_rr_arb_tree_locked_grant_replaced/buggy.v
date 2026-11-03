`timescale 1ns/1ps
module cc_rr_arb_tree(input wire clk_i,input wire rst_ni,input wire [1:0] req_i,input wire ready_i,output reg [1:0] gnt_o);
  reg locked;
  always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin gnt_o<=0;locked<=0; end
    else begin
      // MUTATION: ignores the locked transaction and recomputes grant every cycle.
      if(req_i[0]) gnt_o<=2'b01; else if(req_i[1]) gnt_o<=2'b10; else gnt_o<=0;
      locked<=0;
    end
  end
endmodule
