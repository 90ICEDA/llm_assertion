#!/bin/bash
set -u

cd /home/ibex || exit 1

TEST_NAME="illegal_alu_instr28_exception"
TB_DIR="/home/user/.tb_${TEST_NAME}"
LOG_FILE="${TB_DIR}/sim.log"

mkdir -p "${TB_DIR}"

cat > "${TB_DIR}/tb.sv" <<'EOF'
module tb (
  input  logic clk_i,
  input  logic rst_ni,
  output logic done_o,
  output logic trap_seen_o
);
  logic        instr_req;
  logic        instr_gnt;
  logic        instr_rvalid;
  logic [31:0] instr_addr;
  logic [31:0] instr_rdata;

  logic        data_req;
  logic        data_gnt;
  logic        data_rvalid;
  logic        data_we;
  logic [3:0]  data_be;
  logic [31:0] data_addr;
  logic [31:0] data_wdata;
  logic [31:0] data_rdata;
  logic        data_err;

  logic [31:0] resp_addr_q;
  logic        resp_pending_q;
  int unsigned cycle_count;

  function automatic [31:0] rom_word(input [31:0] addr);
    case (addr)
      32'h0000_0080: rom_word = 32'h1613ac33;
      32'h0000_0084: rom_word = 32'h00000013;
      32'h0000_0088: rom_word = 32'h00000013;
      32'h0000_0000: rom_word = 32'h00000013;
      32'h0000_0004: rom_word = 32'h00000013;
      default: rom_word = 32'h00000013;
    endcase
  endfunction

  ibex_core dut (
    .clk_i          (clk_i),
    .rst_ni         (rst_ni),
    .test_en_i      (1'b0),
    .core_id_i      (4'h0),
    .cluster_id_i   (6'h0),
    .boot_addr_i    (32'h0000_0000),
    .instr_req_o    (instr_req),
    .instr_gnt_i    (instr_gnt),
    .instr_rvalid_i (instr_rvalid),
    .instr_addr_o   (instr_addr),
    .instr_rdata_i  (instr_rdata),
    .data_req_o     (data_req),
    .data_gnt_i     (data_gnt),
    .data_rvalid_i  (data_rvalid),
    .data_we_o      (data_we),
    .data_be_o      (data_be),
    .data_addr_o    (data_addr),
    .data_wdata_o   (data_wdata),
    .data_rdata_i   (data_rdata),
    .data_err_i     (data_err),
    .irq_i          (1'b0),
    .irq_id_i       (5'h0),
    .irq_ack_o      (),
    .irq_id_o       (),
    .debug_req_i    (1'b0),
    .fetch_enable_i (1'b1)
  );

  assign instr_gnt   = instr_req;
  assign data_gnt    = data_req;
  assign data_rvalid = 1'b0;
  assign data_rdata  = 32'h0;
  assign data_err    = 1'b0;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      resp_pending_q <= 1'b0;
      resp_addr_q    <= '0;
      instr_rvalid   <= 1'b0;
      instr_rdata    <= '0;
      cycle_count    <= 0;
      done_o         <= 1'b0;
      trap_seen_o    <= 1'b0;
    end else begin
      cycle_count  <= cycle_count + 1;
      instr_rvalid <= resp_pending_q;

      if (resp_pending_q) begin
        instr_rdata <= rom_word(resp_addr_q);
        $display("FETCH: cycle=%0d addr=0x%08x data=0x%08x", cycle_count, resp_addr_q,
                 rom_word(resp_addr_q));
      end

      resp_pending_q <= instr_req;
      if (instr_req) begin
        resp_addr_q <= instr_addr;
      end

      if (instr_req && instr_addr == 32'h0000_0000 && cycle_count > 2) begin
        done_o      <= 1'b1;
        trap_seen_o <= 1'b1;
      end

      if (cycle_count > 80) begin
        done_o <= 1'b1;
      end
    end
  end
endmodule
EOF

cat > "${TB_DIR}/sim_main.cpp" <<'EOF'
#include "Vtb.h"
#include "verilated.h"

#include <cstdio>

double sc_time_stamp() { return 0; }

static void tick(Vtb &top) {
  top.clk_i = 0;
  top.eval();
  top.clk_i = 1;
  top.eval();
}

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);

  Vtb top;
  top.clk_i = 0;
  top.rst_ni = 0;

  for (int i = 0; i < 5; ++i) {
    tick(top);
  }

  top.rst_ni = 1;

  for (int i = 0; i < 200 && !top.done_o; ++i) {
    tick(top);
  }

  if (!top.done_o || !top.trap_seen_o) {
    std::puts("RESULT: no_trap");
    return 0;
  }

  std::puts("RESULT: trap_taken");
  return 0;
}
EOF

cat > "${TB_DIR}/run_sim.sh" <<'EOF'
#!/bin/bash
set -euo pipefail

cd /home/user/.tb_illegal_alu_instr28_exception

verilator --cc --sv --top-module tb -Wno-fatal -Wno-WIDTH -Wno-UNOPTFLAT \
  -I/home/user/rtl -I/home/user/examples/sim/rtl \
  /home/user/.tb_illegal_alu_instr28_exception/tb.sv \
  /home/user/examples/sim/rtl/prim_clock_gating.sv \
  /home/user/rtl/ibex_defines.sv \
  /home/user/rtl/ibex_tracer_defines.sv \
  /home/user/rtl/ibex_alu.sv \
  /home/user/rtl/ibex_compressed_decoder.sv \
  /home/user/rtl/ibex_controller.sv \
  /home/user/rtl/ibex_cs_registers.sv \
  /home/user/rtl/ibex_decoder.sv \
  /home/user/rtl/ibex_ex_block.sv \
  /home/user/rtl/ibex_fetch_fifo.sv \
  /home/user/rtl/ibex_id_stage.sv \
  /home/user/rtl/ibex_if_stage.sv \
  /home/user/rtl/ibex_int_controller.sv \
  /home/user/rtl/ibex_load_store_unit.sv \
  /home/user/rtl/ibex_multdiv_fast.sv \
  /home/user/rtl/ibex_multdiv_slow.sv \
  /home/user/rtl/ibex_prefetch_buffer.sv \
  /home/user/rtl/ibex_register_file_ff.sv \
  /home/user/rtl/ibex_core.sv \
  --exe /home/user/.tb_illegal_alu_instr28_exception/sim_main.cpp

make -C obj_dir -f Vtb.mk -j"$(nproc)" Vtb
./obj_dir/Vtb
EOF

chmod +x "${TB_DIR}/run_sim.sh"
rm -rf "${TB_DIR}/obj_dir" "${LOG_FILE}"

set +e
timeout 1200s "${TB_DIR}/run_sim.sh" | tee "${LOG_FILE}"
rc=${PIPESTATUS[0]}
set -e

echo "HWE_BENCH_RESULTS_START"
if [ "${rc}" -eq 0 ] && grep -q "RESULT: trap_taken" "${LOG_FILE}"; then
  echo "TEST: ${TEST_NAME} ... PASS"
  echo "HWE_BENCH_RESULTS_END"
  exit 0
fi

echo "TEST: ${TEST_NAME} ... FAIL"
echo "HWE_BENCH_RESULTS_END"
if [ "${rc}" -eq 124 ]; then
  exit 124
fi
exit 1
