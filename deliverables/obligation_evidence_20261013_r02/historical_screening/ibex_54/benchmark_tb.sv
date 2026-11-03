module tb;
  logic [31:0] instr_i;
  logic [31:0] instr_o;
  logic        is_compressed_o;
  logic        illegal_instr_o;
  int          errors = 0;

  ibex_compressed_decoder dut (
    .instr_i(instr_i),
    .instr_o(instr_o),
    .is_compressed_o(is_compressed_o),
    .illegal_instr_o(illegal_instr_o)
  );

  task automatic expect_hint_clear(input string name, input logic [15:0] cinstr);
    begin
      instr_i = {16'h0000, cinstr};
      #1;

      if (is_compressed_o !== 1'b1) begin
        $display("CHECK_FAIL %s compressed=%b instr=%h", name, is_compressed_o, cinstr);
        errors++;
      end

      if (illegal_instr_o !== 1'b0) begin
        $display("CHECK_FAIL %s illegal=%b instr=%h decoded=%h", name, illegal_instr_o, cinstr,
                 instr_o);
        errors++;
      end else begin
        $display("CHECK_PASS %s illegal=%b instr=%h decoded=%h", name, illegal_instr_o, cinstr,
                 instr_o);
      end
    end
  endtask

  initial begin
    expect_hint_clear("c_li_rd_x0_hint",    {3'b010, 1'b0, 5'b00000, 5'b00001, 2'b01});
    expect_hint_clear("c_lui_rd_x0_hint",   16'h7065);
    expect_hint_clear("c_srli_shamt0_hint", {3'b100, 1'b0, 2'b00, 3'b001, 5'b00000, 2'b01});
    expect_hint_clear("c_srai_shamt0_hint", {3'b100, 1'b0, 2'b01, 3'b001, 5'b00000, 2'b01});
    expect_hint_clear("c_slli_shamt0_hint", {3'b000, 1'b0, 5'b00001, 5'b00000, 2'b10});

    if (errors != 0) begin
      $display("TB_FAIL errors=%0d", errors);
      $fatal(1, "compressed hint decoding regression");
    end

    $display("TB_PASS");
    $finish;
  end
endmodule
