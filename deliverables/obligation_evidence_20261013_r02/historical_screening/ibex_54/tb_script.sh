#!/bin/bash
set -uo pipefail

cd /home/ibex || exit 1

TEST_NAME="compressed_hint_decoder"
TB_DIR="/home/user/.tb_${TEST_NAME}"
BUILD_LOG="${TB_DIR}/build.log"
RUN_LOG="${TB_DIR}/run.log"

rm -rf "${TB_DIR}"
mkdir -p "${TB_DIR}"

emit_result() {
  local status="$1"
  local rc="$2"

  echo "HWE_BENCH_RESULTS_START"
  echo "TEST: ${TEST_NAME} ... ${status}"
  echo "HWE_BENCH_RESULTS_END"
  exit "${rc}"
}

cat > "${TB_DIR}/${TEST_NAME}.sv" <<'EOF'
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
EOF

iverilog -g2012 \
  -o "${TB_DIR}/${TEST_NAME}.out" \
  rtl/ibex_defines.sv \
  rtl/ibex_compressed_decoder.sv \
  "${TB_DIR}/${TEST_NAME}.sv" > "${BUILD_LOG}" 2>&1
build_rc=$?

if [ "${build_rc}" -ne 0 ]; then
  cat "${BUILD_LOG}"
  emit_result "FAIL" "${build_rc}"
fi

vvp "${TB_DIR}/${TEST_NAME}.out" 2>&1 | tee "${RUN_LOG}"
run_rc=${PIPESTATUS[0]}

if [ "${run_rc}" -eq 0 ] && grep -q 'TB_PASS' "${RUN_LOG}"; then
  emit_result "PASS" 0
fi

emit_result "FAIL" 1
