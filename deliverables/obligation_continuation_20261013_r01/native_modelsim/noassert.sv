`timescale 1ns/1ps
module noassert;
initial begin
  $display("NOASSERT_START");
  #1;
  $display("NOASSERT_TIME_ADVANCED");
  #1;
  $finish;
end
endmodule
