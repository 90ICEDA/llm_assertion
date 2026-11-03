module tb; reg [31:0] instr_i; wire [31:0] instr_o; wire is_compressed_o,illegal_instr_o;
integer errors=0; ibex_compressed_decoder dut(.*); initial begin
$dumpfile("wave.vcd"); $dumpvars(0,tb);
instr_i=32'h00004001; #1;
$display("TRACE 0 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00000013) begin errors=errors+1; $display("BOUNDARY_FAIL 0"); end
instr_i=32'h00006001; #1;
$display("TRACE 1 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 1"); end
instr_i=32'h00004005; #1;
$display("TRACE 2 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00100013) begin errors=errors+1; $display("BOUNDARY_FAIL 2"); end
instr_i=32'h00006005; #1;
$display("TRACE 3 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00001037) begin errors=errors+1; $display("BOUNDARY_FAIL 3"); end
instr_i=32'h00004009; #1;
$display("TRACE 4 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00200013) begin errors=errors+1; $display("BOUNDARY_FAIL 4"); end
instr_i=32'h00006009; #1;
$display("TRACE 5 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00002037) begin errors=errors+1; $display("BOUNDARY_FAIL 5"); end
instr_i=32'h0000400d; #1;
$display("TRACE 6 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00300013) begin errors=errors+1; $display("BOUNDARY_FAIL 6"); end
instr_i=32'h0000600d; #1;
$display("TRACE 7 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00003037) begin errors=errors+1; $display("BOUNDARY_FAIL 7"); end
instr_i=32'h00004011; #1;
$display("TRACE 8 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00400013) begin errors=errors+1; $display("BOUNDARY_FAIL 8"); end
instr_i=32'h00006011; #1;
$display("TRACE 9 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00004037) begin errors=errors+1; $display("BOUNDARY_FAIL 9"); end
instr_i=32'h00004015; #1;
$display("TRACE 10 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00500013) begin errors=errors+1; $display("BOUNDARY_FAIL 10"); end
instr_i=32'h00006015; #1;
$display("TRACE 11 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00005037) begin errors=errors+1; $display("BOUNDARY_FAIL 11"); end
instr_i=32'h00004019; #1;
$display("TRACE 12 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00600013) begin errors=errors+1; $display("BOUNDARY_FAIL 12"); end
instr_i=32'h00006019; #1;
$display("TRACE 13 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00006037) begin errors=errors+1; $display("BOUNDARY_FAIL 13"); end
instr_i=32'h0000401d; #1;
$display("TRACE 14 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00700013) begin errors=errors+1; $display("BOUNDARY_FAIL 14"); end
instr_i=32'h0000601d; #1;
$display("TRACE 15 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00007037) begin errors=errors+1; $display("BOUNDARY_FAIL 15"); end
instr_i=32'h00004021; #1;
$display("TRACE 16 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00800013) begin errors=errors+1; $display("BOUNDARY_FAIL 16"); end
instr_i=32'h00006021; #1;
$display("TRACE 17 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00008037) begin errors=errors+1; $display("BOUNDARY_FAIL 17"); end
instr_i=32'h00004025; #1;
$display("TRACE 18 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00900013) begin errors=errors+1; $display("BOUNDARY_FAIL 18"); end
instr_i=32'h00006025; #1;
$display("TRACE 19 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00009037) begin errors=errors+1; $display("BOUNDARY_FAIL 19"); end
instr_i=32'h00004029; #1;
$display("TRACE 20 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00a00013) begin errors=errors+1; $display("BOUNDARY_FAIL 20"); end
instr_i=32'h00006029; #1;
$display("TRACE 21 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0000a037) begin errors=errors+1; $display("BOUNDARY_FAIL 21"); end
instr_i=32'h0000402d; #1;
$display("TRACE 22 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00b00013) begin errors=errors+1; $display("BOUNDARY_FAIL 22"); end
instr_i=32'h0000602d; #1;
$display("TRACE 23 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0000b037) begin errors=errors+1; $display("BOUNDARY_FAIL 23"); end
instr_i=32'h00004031; #1;
$display("TRACE 24 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00c00013) begin errors=errors+1; $display("BOUNDARY_FAIL 24"); end
instr_i=32'h00006031; #1;
$display("TRACE 25 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0000c037) begin errors=errors+1; $display("BOUNDARY_FAIL 25"); end
instr_i=32'h00004035; #1;
$display("TRACE 26 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00d00013) begin errors=errors+1; $display("BOUNDARY_FAIL 26"); end
instr_i=32'h00006035; #1;
$display("TRACE 27 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0000d037) begin errors=errors+1; $display("BOUNDARY_FAIL 27"); end
instr_i=32'h00004039; #1;
$display("TRACE 28 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00e00013) begin errors=errors+1; $display("BOUNDARY_FAIL 28"); end
instr_i=32'h00006039; #1;
$display("TRACE 29 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0000e037) begin errors=errors+1; $display("BOUNDARY_FAIL 29"); end
instr_i=32'h0000403d; #1;
$display("TRACE 30 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00f00013) begin errors=errors+1; $display("BOUNDARY_FAIL 30"); end
instr_i=32'h0000603d; #1;
$display("TRACE 31 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0000f037) begin errors=errors+1; $display("BOUNDARY_FAIL 31"); end
instr_i=32'h00004041; #1;
$display("TRACE 32 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01000013) begin errors=errors+1; $display("BOUNDARY_FAIL 32"); end
instr_i=32'h00006041; #1;
$display("TRACE 33 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00010037) begin errors=errors+1; $display("BOUNDARY_FAIL 33"); end
instr_i=32'h00004045; #1;
$display("TRACE 34 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01100013) begin errors=errors+1; $display("BOUNDARY_FAIL 34"); end
instr_i=32'h00006045; #1;
$display("TRACE 35 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00011037) begin errors=errors+1; $display("BOUNDARY_FAIL 35"); end
instr_i=32'h00004049; #1;
$display("TRACE 36 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01200013) begin errors=errors+1; $display("BOUNDARY_FAIL 36"); end
instr_i=32'h00006049; #1;
$display("TRACE 37 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00012037) begin errors=errors+1; $display("BOUNDARY_FAIL 37"); end
instr_i=32'h0000404d; #1;
$display("TRACE 38 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01300013) begin errors=errors+1; $display("BOUNDARY_FAIL 38"); end
instr_i=32'h0000604d; #1;
$display("TRACE 39 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00013037) begin errors=errors+1; $display("BOUNDARY_FAIL 39"); end
instr_i=32'h00004051; #1;
$display("TRACE 40 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01400013) begin errors=errors+1; $display("BOUNDARY_FAIL 40"); end
instr_i=32'h00006051; #1;
$display("TRACE 41 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00014037) begin errors=errors+1; $display("BOUNDARY_FAIL 41"); end
instr_i=32'h00004055; #1;
$display("TRACE 42 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01500013) begin errors=errors+1; $display("BOUNDARY_FAIL 42"); end
instr_i=32'h00006055; #1;
$display("TRACE 43 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00015037) begin errors=errors+1; $display("BOUNDARY_FAIL 43"); end
instr_i=32'h00004059; #1;
$display("TRACE 44 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01600013) begin errors=errors+1; $display("BOUNDARY_FAIL 44"); end
instr_i=32'h00006059; #1;
$display("TRACE 45 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00016037) begin errors=errors+1; $display("BOUNDARY_FAIL 45"); end
instr_i=32'h0000405d; #1;
$display("TRACE 46 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01700013) begin errors=errors+1; $display("BOUNDARY_FAIL 46"); end
instr_i=32'h0000605d; #1;
$display("TRACE 47 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00017037) begin errors=errors+1; $display("BOUNDARY_FAIL 47"); end
instr_i=32'h00004061; #1;
$display("TRACE 48 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01800013) begin errors=errors+1; $display("BOUNDARY_FAIL 48"); end
instr_i=32'h00006061; #1;
$display("TRACE 49 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00018037) begin errors=errors+1; $display("BOUNDARY_FAIL 49"); end
instr_i=32'h00004065; #1;
$display("TRACE 50 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01900013) begin errors=errors+1; $display("BOUNDARY_FAIL 50"); end
instr_i=32'h00006065; #1;
$display("TRACE 51 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00019037) begin errors=errors+1; $display("BOUNDARY_FAIL 51"); end
instr_i=32'h00004069; #1;
$display("TRACE 52 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01a00013) begin errors=errors+1; $display("BOUNDARY_FAIL 52"); end
instr_i=32'h00006069; #1;
$display("TRACE 53 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0001a037) begin errors=errors+1; $display("BOUNDARY_FAIL 53"); end
instr_i=32'h0000406d; #1;
$display("TRACE 54 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01b00013) begin errors=errors+1; $display("BOUNDARY_FAIL 54"); end
instr_i=32'h0000606d; #1;
$display("TRACE 55 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0001b037) begin errors=errors+1; $display("BOUNDARY_FAIL 55"); end
instr_i=32'h00004071; #1;
$display("TRACE 56 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01c00013) begin errors=errors+1; $display("BOUNDARY_FAIL 56"); end
instr_i=32'h00006071; #1;
$display("TRACE 57 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0001c037) begin errors=errors+1; $display("BOUNDARY_FAIL 57"); end
instr_i=32'h00004075; #1;
$display("TRACE 58 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01d00013) begin errors=errors+1; $display("BOUNDARY_FAIL 58"); end
instr_i=32'h00006075; #1;
$display("TRACE 59 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0001d037) begin errors=errors+1; $display("BOUNDARY_FAIL 59"); end
instr_i=32'h00004079; #1;
$display("TRACE 60 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01e00013) begin errors=errors+1; $display("BOUNDARY_FAIL 60"); end
instr_i=32'h00006079; #1;
$display("TRACE 61 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0001e037) begin errors=errors+1; $display("BOUNDARY_FAIL 61"); end
instr_i=32'h0000407d; #1;
$display("TRACE 62 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h01f00013) begin errors=errors+1; $display("BOUNDARY_FAIL 62"); end
instr_i=32'h0000607d; #1;
$display("TRACE 63 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0001f037) begin errors=errors+1; $display("BOUNDARY_FAIL 63"); end
instr_i=32'h00005001; #1;
$display("TRACE 64 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe000013) begin errors=errors+1; $display("BOUNDARY_FAIL 64"); end
instr_i=32'h00007001; #1;
$display("TRACE 65 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe0037) begin errors=errors+1; $display("BOUNDARY_FAIL 65"); end
instr_i=32'h00005005; #1;
$display("TRACE 66 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe100013) begin errors=errors+1; $display("BOUNDARY_FAIL 66"); end
instr_i=32'h00007005; #1;
$display("TRACE 67 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe1037) begin errors=errors+1; $display("BOUNDARY_FAIL 67"); end
instr_i=32'h00005009; #1;
$display("TRACE 68 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe200013) begin errors=errors+1; $display("BOUNDARY_FAIL 68"); end
instr_i=32'h00007009; #1;
$display("TRACE 69 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe2037) begin errors=errors+1; $display("BOUNDARY_FAIL 69"); end
instr_i=32'h0000500d; #1;
$display("TRACE 70 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe300013) begin errors=errors+1; $display("BOUNDARY_FAIL 70"); end
instr_i=32'h0000700d; #1;
$display("TRACE 71 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe3037) begin errors=errors+1; $display("BOUNDARY_FAIL 71"); end
instr_i=32'h00005011; #1;
$display("TRACE 72 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe400013) begin errors=errors+1; $display("BOUNDARY_FAIL 72"); end
instr_i=32'h00007011; #1;
$display("TRACE 73 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe4037) begin errors=errors+1; $display("BOUNDARY_FAIL 73"); end
instr_i=32'h00005015; #1;
$display("TRACE 74 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe500013) begin errors=errors+1; $display("BOUNDARY_FAIL 74"); end
instr_i=32'h00007015; #1;
$display("TRACE 75 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe5037) begin errors=errors+1; $display("BOUNDARY_FAIL 75"); end
instr_i=32'h00005019; #1;
$display("TRACE 76 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe600013) begin errors=errors+1; $display("BOUNDARY_FAIL 76"); end
instr_i=32'h00007019; #1;
$display("TRACE 77 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe6037) begin errors=errors+1; $display("BOUNDARY_FAIL 77"); end
instr_i=32'h0000501d; #1;
$display("TRACE 78 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe700013) begin errors=errors+1; $display("BOUNDARY_FAIL 78"); end
instr_i=32'h0000701d; #1;
$display("TRACE 79 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe7037) begin errors=errors+1; $display("BOUNDARY_FAIL 79"); end
instr_i=32'h00005021; #1;
$display("TRACE 80 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe800013) begin errors=errors+1; $display("BOUNDARY_FAIL 80"); end
instr_i=32'h00007021; #1;
$display("TRACE 81 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe8037) begin errors=errors+1; $display("BOUNDARY_FAIL 81"); end
instr_i=32'h00005025; #1;
$display("TRACE 82 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfe900013) begin errors=errors+1; $display("BOUNDARY_FAIL 82"); end
instr_i=32'h00007025; #1;
$display("TRACE 83 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffe9037) begin errors=errors+1; $display("BOUNDARY_FAIL 83"); end
instr_i=32'h00005029; #1;
$display("TRACE 84 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfea00013) begin errors=errors+1; $display("BOUNDARY_FAIL 84"); end
instr_i=32'h00007029; #1;
$display("TRACE 85 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffea037) begin errors=errors+1; $display("BOUNDARY_FAIL 85"); end
instr_i=32'h0000502d; #1;
$display("TRACE 86 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfeb00013) begin errors=errors+1; $display("BOUNDARY_FAIL 86"); end
instr_i=32'h0000702d; #1;
$display("TRACE 87 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffeb037) begin errors=errors+1; $display("BOUNDARY_FAIL 87"); end
instr_i=32'h00005031; #1;
$display("TRACE 88 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfec00013) begin errors=errors+1; $display("BOUNDARY_FAIL 88"); end
instr_i=32'h00007031; #1;
$display("TRACE 89 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffec037) begin errors=errors+1; $display("BOUNDARY_FAIL 89"); end
instr_i=32'h00005035; #1;
$display("TRACE 90 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfed00013) begin errors=errors+1; $display("BOUNDARY_FAIL 90"); end
instr_i=32'h00007035; #1;
$display("TRACE 91 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffed037) begin errors=errors+1; $display("BOUNDARY_FAIL 91"); end
instr_i=32'h00005039; #1;
$display("TRACE 92 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfee00013) begin errors=errors+1; $display("BOUNDARY_FAIL 92"); end
instr_i=32'h00007039; #1;
$display("TRACE 93 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffee037) begin errors=errors+1; $display("BOUNDARY_FAIL 93"); end
instr_i=32'h0000503d; #1;
$display("TRACE 94 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfef00013) begin errors=errors+1; $display("BOUNDARY_FAIL 94"); end
instr_i=32'h0000703d; #1;
$display("TRACE 95 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffef037) begin errors=errors+1; $display("BOUNDARY_FAIL 95"); end
instr_i=32'h00005041; #1;
$display("TRACE 96 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff000013) begin errors=errors+1; $display("BOUNDARY_FAIL 96"); end
instr_i=32'h00007041; #1;
$display("TRACE 97 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff0037) begin errors=errors+1; $display("BOUNDARY_FAIL 97"); end
instr_i=32'h00005045; #1;
$display("TRACE 98 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff100013) begin errors=errors+1; $display("BOUNDARY_FAIL 98"); end
instr_i=32'h00007045; #1;
$display("TRACE 99 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff1037) begin errors=errors+1; $display("BOUNDARY_FAIL 99"); end
instr_i=32'h00005049; #1;
$display("TRACE 100 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff200013) begin errors=errors+1; $display("BOUNDARY_FAIL 100"); end
instr_i=32'h00007049; #1;
$display("TRACE 101 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff2037) begin errors=errors+1; $display("BOUNDARY_FAIL 101"); end
instr_i=32'h0000504d; #1;
$display("TRACE 102 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff300013) begin errors=errors+1; $display("BOUNDARY_FAIL 102"); end
instr_i=32'h0000704d; #1;
$display("TRACE 103 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff3037) begin errors=errors+1; $display("BOUNDARY_FAIL 103"); end
instr_i=32'h00005051; #1;
$display("TRACE 104 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff400013) begin errors=errors+1; $display("BOUNDARY_FAIL 104"); end
instr_i=32'h00007051; #1;
$display("TRACE 105 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff4037) begin errors=errors+1; $display("BOUNDARY_FAIL 105"); end
instr_i=32'h00005055; #1;
$display("TRACE 106 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff500013) begin errors=errors+1; $display("BOUNDARY_FAIL 106"); end
instr_i=32'h00007055; #1;
$display("TRACE 107 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff5037) begin errors=errors+1; $display("BOUNDARY_FAIL 107"); end
instr_i=32'h00005059; #1;
$display("TRACE 108 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff600013) begin errors=errors+1; $display("BOUNDARY_FAIL 108"); end
instr_i=32'h00007059; #1;
$display("TRACE 109 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff6037) begin errors=errors+1; $display("BOUNDARY_FAIL 109"); end
instr_i=32'h0000505d; #1;
$display("TRACE 110 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff700013) begin errors=errors+1; $display("BOUNDARY_FAIL 110"); end
instr_i=32'h0000705d; #1;
$display("TRACE 111 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff7037) begin errors=errors+1; $display("BOUNDARY_FAIL 111"); end
instr_i=32'h00005061; #1;
$display("TRACE 112 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff800013) begin errors=errors+1; $display("BOUNDARY_FAIL 112"); end
instr_i=32'h00007061; #1;
$display("TRACE 113 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff8037) begin errors=errors+1; $display("BOUNDARY_FAIL 113"); end
instr_i=32'h00005065; #1;
$display("TRACE 114 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hff900013) begin errors=errors+1; $display("BOUNDARY_FAIL 114"); end
instr_i=32'h00007065; #1;
$display("TRACE 115 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff9037) begin errors=errors+1; $display("BOUNDARY_FAIL 115"); end
instr_i=32'h00005069; #1;
$display("TRACE 116 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffa00013) begin errors=errors+1; $display("BOUNDARY_FAIL 116"); end
instr_i=32'h00007069; #1;
$display("TRACE 117 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffffa037) begin errors=errors+1; $display("BOUNDARY_FAIL 117"); end
instr_i=32'h0000506d; #1;
$display("TRACE 118 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffb00013) begin errors=errors+1; $display("BOUNDARY_FAIL 118"); end
instr_i=32'h0000706d; #1;
$display("TRACE 119 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffffb037) begin errors=errors+1; $display("BOUNDARY_FAIL 119"); end
instr_i=32'h00005071; #1;
$display("TRACE 120 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffc00013) begin errors=errors+1; $display("BOUNDARY_FAIL 120"); end
instr_i=32'h00007071; #1;
$display("TRACE 121 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffffc037) begin errors=errors+1; $display("BOUNDARY_FAIL 121"); end
instr_i=32'h00005075; #1;
$display("TRACE 122 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffd00013) begin errors=errors+1; $display("BOUNDARY_FAIL 122"); end
instr_i=32'h00007075; #1;
$display("TRACE 123 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffffd037) begin errors=errors+1; $display("BOUNDARY_FAIL 123"); end
instr_i=32'h00005079; #1;
$display("TRACE 124 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffe00013) begin errors=errors+1; $display("BOUNDARY_FAIL 124"); end
instr_i=32'h00007079; #1;
$display("TRACE 125 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffffe037) begin errors=errors+1; $display("BOUNDARY_FAIL 125"); end
instr_i=32'h0000507d; #1;
$display("TRACE 126 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfff00013) begin errors=errors+1; $display("BOUNDARY_FAIL 126"); end
instr_i=32'h0000707d; #1;
$display("TRACE 127 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hfffff037) begin errors=errors+1; $display("BOUNDARY_FAIL 127"); end
instr_i=32'h00008001; #1;
$display("TRACE 128 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00045413) begin errors=errors+1; $display("BOUNDARY_FAIL 128"); end
instr_i=32'h00009001; #1;
$display("TRACE 129 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 129"); end
instr_i=32'h00008401; #1;
$display("TRACE 130 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h40045413) begin errors=errors+1; $display("BOUNDARY_FAIL 130"); end
instr_i=32'h00009401; #1;
$display("TRACE 131 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 131"); end
instr_i=32'h00008081; #1;
$display("TRACE 132 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0004d493) begin errors=errors+1; $display("BOUNDARY_FAIL 132"); end
instr_i=32'h00009081; #1;
$display("TRACE 133 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 133"); end
instr_i=32'h00008481; #1;
$display("TRACE 134 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h4004d493) begin errors=errors+1; $display("BOUNDARY_FAIL 134"); end
instr_i=32'h00009481; #1;
$display("TRACE 135 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 135"); end
instr_i=32'h00008101; #1;
$display("TRACE 136 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00055513) begin errors=errors+1; $display("BOUNDARY_FAIL 136"); end
instr_i=32'h00009101; #1;
$display("TRACE 137 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 137"); end
instr_i=32'h00008501; #1;
$display("TRACE 138 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h40055513) begin errors=errors+1; $display("BOUNDARY_FAIL 138"); end
instr_i=32'h00009501; #1;
$display("TRACE 139 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 139"); end
instr_i=32'h00008181; #1;
$display("TRACE 140 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0005d593) begin errors=errors+1; $display("BOUNDARY_FAIL 140"); end
instr_i=32'h00009181; #1;
$display("TRACE 141 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 141"); end
instr_i=32'h00008581; #1;
$display("TRACE 142 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h4005d593) begin errors=errors+1; $display("BOUNDARY_FAIL 142"); end
instr_i=32'h00009581; #1;
$display("TRACE 143 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 143"); end
instr_i=32'h00008201; #1;
$display("TRACE 144 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00065613) begin errors=errors+1; $display("BOUNDARY_FAIL 144"); end
instr_i=32'h00009201; #1;
$display("TRACE 145 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 145"); end
instr_i=32'h00008601; #1;
$display("TRACE 146 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h40065613) begin errors=errors+1; $display("BOUNDARY_FAIL 146"); end
instr_i=32'h00009601; #1;
$display("TRACE 147 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 147"); end
instr_i=32'h00008281; #1;
$display("TRACE 148 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0006d693) begin errors=errors+1; $display("BOUNDARY_FAIL 148"); end
instr_i=32'h00009281; #1;
$display("TRACE 149 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 149"); end
instr_i=32'h00008681; #1;
$display("TRACE 150 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h4006d693) begin errors=errors+1; $display("BOUNDARY_FAIL 150"); end
instr_i=32'h00009681; #1;
$display("TRACE 151 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 151"); end
instr_i=32'h00008301; #1;
$display("TRACE 152 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00075713) begin errors=errors+1; $display("BOUNDARY_FAIL 152"); end
instr_i=32'h00009301; #1;
$display("TRACE 153 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 153"); end
instr_i=32'h00008701; #1;
$display("TRACE 154 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h40075713) begin errors=errors+1; $display("BOUNDARY_FAIL 154"); end
instr_i=32'h00009701; #1;
$display("TRACE 155 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 155"); end
instr_i=32'h00008381; #1;
$display("TRACE 156 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h0007d793) begin errors=errors+1; $display("BOUNDARY_FAIL 156"); end
instr_i=32'h00009381; #1;
$display("TRACE 157 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 157"); end
instr_i=32'h00008781; #1;
$display("TRACE 158 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h4007d793) begin errors=errors+1; $display("BOUNDARY_FAIL 158"); end
instr_i=32'h00009781; #1;
$display("TRACE 159 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 159"); end
instr_i=32'h00000082; #1;
$display("TRACE 160 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00009093) begin errors=errors+1; $display("BOUNDARY_FAIL 160"); end
instr_i=32'h00001082; #1;
$display("TRACE 161 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 161"); end
instr_i=32'h00000102; #1;
$display("TRACE 162 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00011113) begin errors=errors+1; $display("BOUNDARY_FAIL 162"); end
instr_i=32'h00001102; #1;
$display("TRACE 163 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 163"); end
instr_i=32'h00000182; #1;
$display("TRACE 164 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00019193) begin errors=errors+1; $display("BOUNDARY_FAIL 164"); end
instr_i=32'h00001182; #1;
$display("TRACE 165 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 165"); end
instr_i=32'h00000202; #1;
$display("TRACE 166 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00021213) begin errors=errors+1; $display("BOUNDARY_FAIL 166"); end
instr_i=32'h00001202; #1;
$display("TRACE 167 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 167"); end
instr_i=32'h00000282; #1;
$display("TRACE 168 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00029293) begin errors=errors+1; $display("BOUNDARY_FAIL 168"); end
instr_i=32'h00001282; #1;
$display("TRACE 169 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 169"); end
instr_i=32'h00000302; #1;
$display("TRACE 170 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00031313) begin errors=errors+1; $display("BOUNDARY_FAIL 170"); end
instr_i=32'h00001302; #1;
$display("TRACE 171 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 171"); end
instr_i=32'h00000382; #1;
$display("TRACE 172 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00039393) begin errors=errors+1; $display("BOUNDARY_FAIL 172"); end
instr_i=32'h00001382; #1;
$display("TRACE 173 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 173"); end
instr_i=32'h00000402; #1;
$display("TRACE 174 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00041413) begin errors=errors+1; $display("BOUNDARY_FAIL 174"); end
instr_i=32'h00001402; #1;
$display("TRACE 175 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 175"); end
instr_i=32'h00000482; #1;
$display("TRACE 176 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00049493) begin errors=errors+1; $display("BOUNDARY_FAIL 176"); end
instr_i=32'h00001482; #1;
$display("TRACE 177 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 177"); end
instr_i=32'h00000502; #1;
$display("TRACE 178 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00051513) begin errors=errors+1; $display("BOUNDARY_FAIL 178"); end
instr_i=32'h00001502; #1;
$display("TRACE 179 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 179"); end
instr_i=32'h00000582; #1;
$display("TRACE 180 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00059593) begin errors=errors+1; $display("BOUNDARY_FAIL 180"); end
instr_i=32'h00001582; #1;
$display("TRACE 181 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 181"); end
instr_i=32'h00000602; #1;
$display("TRACE 182 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00061613) begin errors=errors+1; $display("BOUNDARY_FAIL 182"); end
instr_i=32'h00001602; #1;
$display("TRACE 183 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 183"); end
instr_i=32'h00000682; #1;
$display("TRACE 184 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00069693) begin errors=errors+1; $display("BOUNDARY_FAIL 184"); end
instr_i=32'h00001682; #1;
$display("TRACE 185 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 185"); end
instr_i=32'h00000702; #1;
$display("TRACE 186 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00071713) begin errors=errors+1; $display("BOUNDARY_FAIL 186"); end
instr_i=32'h00001702; #1;
$display("TRACE 187 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 187"); end
instr_i=32'h00000782; #1;
$display("TRACE 188 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00079793) begin errors=errors+1; $display("BOUNDARY_FAIL 188"); end
instr_i=32'h00001782; #1;
$display("TRACE 189 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 189"); end
instr_i=32'h00000802; #1;
$display("TRACE 190 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00081813) begin errors=errors+1; $display("BOUNDARY_FAIL 190"); end
instr_i=32'h00001802; #1;
$display("TRACE 191 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 191"); end
instr_i=32'h00000882; #1;
$display("TRACE 192 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00089893) begin errors=errors+1; $display("BOUNDARY_FAIL 192"); end
instr_i=32'h00001882; #1;
$display("TRACE 193 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 193"); end
instr_i=32'h00000902; #1;
$display("TRACE 194 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00091913) begin errors=errors+1; $display("BOUNDARY_FAIL 194"); end
instr_i=32'h00001902; #1;
$display("TRACE 195 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 195"); end
instr_i=32'h00000982; #1;
$display("TRACE 196 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h00099993) begin errors=errors+1; $display("BOUNDARY_FAIL 196"); end
instr_i=32'h00001982; #1;
$display("TRACE 197 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 197"); end
instr_i=32'h00000a02; #1;
$display("TRACE 198 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000a1a13) begin errors=errors+1; $display("BOUNDARY_FAIL 198"); end
instr_i=32'h00001a02; #1;
$display("TRACE 199 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 199"); end
instr_i=32'h00000a82; #1;
$display("TRACE 200 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000a9a93) begin errors=errors+1; $display("BOUNDARY_FAIL 200"); end
instr_i=32'h00001a82; #1;
$display("TRACE 201 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 201"); end
instr_i=32'h00000b02; #1;
$display("TRACE 202 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000b1b13) begin errors=errors+1; $display("BOUNDARY_FAIL 202"); end
instr_i=32'h00001b02; #1;
$display("TRACE 203 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 203"); end
instr_i=32'h00000b82; #1;
$display("TRACE 204 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000b9b93) begin errors=errors+1; $display("BOUNDARY_FAIL 204"); end
instr_i=32'h00001b82; #1;
$display("TRACE 205 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 205"); end
instr_i=32'h00000c02; #1;
$display("TRACE 206 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000c1c13) begin errors=errors+1; $display("BOUNDARY_FAIL 206"); end
instr_i=32'h00001c02; #1;
$display("TRACE 207 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 207"); end
instr_i=32'h00000c82; #1;
$display("TRACE 208 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000c9c93) begin errors=errors+1; $display("BOUNDARY_FAIL 208"); end
instr_i=32'h00001c82; #1;
$display("TRACE 209 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 209"); end
instr_i=32'h00000d02; #1;
$display("TRACE 210 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000d1d13) begin errors=errors+1; $display("BOUNDARY_FAIL 210"); end
instr_i=32'h00001d02; #1;
$display("TRACE 211 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 211"); end
instr_i=32'h00000d82; #1;
$display("TRACE 212 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000d9d93) begin errors=errors+1; $display("BOUNDARY_FAIL 212"); end
instr_i=32'h00001d82; #1;
$display("TRACE 213 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 213"); end
instr_i=32'h00000e02; #1;
$display("TRACE 214 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000e1e13) begin errors=errors+1; $display("BOUNDARY_FAIL 214"); end
instr_i=32'h00001e02; #1;
$display("TRACE 215 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 215"); end
instr_i=32'h00000e82; #1;
$display("TRACE 216 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000e9e93) begin errors=errors+1; $display("BOUNDARY_FAIL 216"); end
instr_i=32'h00001e82; #1;
$display("TRACE 217 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 217"); end
instr_i=32'h00000f02; #1;
$display("TRACE 218 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000f1f13) begin errors=errors+1; $display("BOUNDARY_FAIL 218"); end
instr_i=32'h00001f02; #1;
$display("TRACE 219 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 219"); end
instr_i=32'h00000f82; #1;
$display("TRACE 220 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'h000f9f93) begin errors=errors+1; $display("BOUNDARY_FAIL 220"); end
instr_i=32'h00001f82; #1;
$display("TRACE 221 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b1 || is_compressed_o !== 1'b1) begin errors=errors+1; $display("BOUNDARY_FAIL 221"); end
instr_i=32'h00007065; #1;
$display("TRACE 222 input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);
if (illegal_instr_o !== 1'b0 || is_compressed_o !== 1'b1 || instr_o !== 32'hffff9037) begin errors=errors+1; $display("BOUNDARY_FAIL 222"); end
$display("BOUNDARY_ERRORS %0d",errors); if(errors) $fatal(1,"boundary checks"); $finish; end endmodule
