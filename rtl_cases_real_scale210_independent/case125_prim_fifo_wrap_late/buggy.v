// Auto-generated real RTL mutation scaffold.
// case: case125_prim_fifo_wrap_late
// source_project: opentitan
// source_module: prim_fifo_sync_cnt

`ifndef ASSERT_DEFAULT_CLK
`define ASSERT_DEFAULT_CLK clk_i
`endif
`ifndef ASSERT_DEFAULT_RST
`define ASSERT_DEFAULT_RST !rst_ni
`endif
`ifndef ASSERT_I
`define ASSERT_I(__name, __prop)
`endif
`ifndef ASSERT_INIT
`define ASSERT_INIT(__name, __prop)
`endif
`ifndef ASSERT_INIT_NET
`define ASSERT_INIT_NET(__name, __prop)
`endif
`ifndef ASSERT_FINAL
`define ASSERT_FINAL(__name, __prop)
`endif
`ifndef ASSERT_AT_RESET
`define ASSERT_AT_RESET(__name, __prop, __rst = `ASSERT_DEFAULT_RST)
`endif
`ifndef ASSERT_AT_RESET_AND_FINAL
`define ASSERT_AT_RESET_AND_FINAL(__name, __prop, __rst = `ASSERT_DEFAULT_RST)
`endif
`ifndef ASSERT
`define ASSERT(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)
`endif
`ifndef ASSERT_NEVER
`define ASSERT_NEVER(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)
`endif
`ifndef ASSERT_KNOWN
`define ASSERT_KNOWN(__name, __sig, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)
`endif
`ifndef COVER
`define COVER(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)
`endif
`ifndef ASSUME
`define ASSUME(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)
`endif
`ifndef ASSUME_I
`define ASSUME_I(__name, __prop)
`endif
`ifndef ASSUME_FPV
`define ASSUME_FPV(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)
`endif

module dut_case125_prim_fifo_wrap_late (
  input logic clk,
  input logic rst_n,
  input logic clr_i,
  input logic incr_wptr_i,
  input logic incr_rptr_i,
  output logic [1:0] wptr_o,
  output logic [1:0] rptr_o,
  output logic full_o,
  output logic empty_o,
  output logic [2:0] depth_o,
  output logic err_o
);
  prim_fifo_sync_cnt #(
    .Depth(4),
    .Secure(1'b0),
    .NeverClears(1'b0)
  ) u_dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .clr_i(clr_i),
    .incr_wptr_i(incr_wptr_i),
    .incr_rptr_i(incr_rptr_i),
    .wptr_o(wptr_o),
    .rptr_o(rptr_o),
    .full_o(full_o),
    .empty_o(empty_o),
    .depth_o(depth_o),
    .err_o(err_o)
  );
endmodule

// ----- source: /mnt/d/AssertionForge-main/external/opentitan/hw/ip/prim/rtl/prim_util_pkg.sv -----
// Copyright lowRISC contributors (OpenTitan project).
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0


/**
 * Utility functions
 */
package prim_util_pkg;
  /**
   * Math function: Number of bits needed to address |value| items.
   *
   *                  0        for value == 0
   * vbits =          1        for value == 1
   *         ceil(log2(value)) for value > 1
   *
   *
   * The primary use case for this function is the definition of registers/arrays
   * which are wide enough to contain |value| items.
   *
   * This function identical to $clog2() for all input values except the value 1;
   * it could be considered an "enhanced" $clog2() function.
   *
   *
   * Example 1:
   *   parameter Items = 1;
   *   localparam ItemsWidth = vbits(Items); // 1
   *   logic [ItemsWidth-1:0] item_register; // items_register is now [0:0]
   *
   * Example 2:
   *   parameter Items = 64;
   *   localparam ItemsWidth = vbits(Items); // 6
   *   logic [ItemsWidth-1:0] item_register; // items_register is now [5:0]
   *
   * Note: If you want to store the number "value" inside a register, you need
   * a register with size vbits(value + 1), since you also need to store
   * the number 0.
   *
   * Example 3:
   *   logic [vbits(64)-1:0]     store_64_logic_values; // width is [5:0]
   *   logic [vbits(64 + 1)-1:0] store_number_64;       // width is [6:0]
   */
  function automatic integer vbits(integer value);
    return (value == 1) ? 1 : $clog2(value);
  endfunction

  /**
   * Computes the ceiling division of two integer values.
   *
   * This function performs integer division and rounds the result up to the nearest integer.
   * It effectively computes the smallest integer greater than or equal to dividend / divisor.
   *
   * @param dividend The integer dividend.
   * @param divisor The integer divisor.
   * @return The ceiling division result (dividend / divisor, rounded up).
   *
   * Example:
   * ceil_div(10, 3) returns 4
   * ceil_div(12, 4) returns 3
   * ceil_div(15, 6) returns 3
   */
  function automatic integer ceil_div(input integer dividend, input integer divisor);
    ceil_div = ((dividend % divisor) != 0) ? (dividend / divisor) + 1 : (dividend / divisor);
  endfunction

`ifdef INC_ASSERT
  // Package-scoped variable to detect the end of simulation.
  //
  // Used only in DV simulations. The bit will be used by assertions in RTL to perform end-of-test
  // cleanup. It is set to 1 in `dv_test_status_pkg::dv_test_status()`, which is invoked right
  // before the simulation is terminated, to signal the status of the test.
  bit end_of_simulation;
`endif

endpackage

// ----- mutated source: /mnt/d/AssertionForge-main/external/opentitan/hw/ip/prim/rtl/prim_fifo_sync_cnt.sv -----
// Copyright lowRISC contributors (OpenTitan project).
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
//
// Read and write pointer logic for synchronous FIFOs

module prim_fifo_sync_cnt #(
  // Depth of the FIFO, i.e., maximum number of entries the FIFO can contain
  parameter int unsigned Depth = 4,
  // Whether to instantiate hardened counters
  parameter bit Secure = 1'b0,
  // If this is set, the clr_i port will always be false
  parameter bit NeverClears = 1'b0,
  // Width of the read and write pointers for the FIFO
  localparam int unsigned PtrW = prim_util_pkg::vbits(Depth),
  // Width of the 'current depth' output
  localparam int unsigned DepthW = prim_util_pkg::vbits(Depth+1)
) (
  input clk_i,
  input rst_ni,
  input clr_i,
  input incr_wptr_i,
  input incr_rptr_i,
  // Write and read pointers.  Value range: [0, Depth-1]
  output logic [PtrW-1:0] wptr_o,
  output logic [PtrW-1:0] rptr_o,
  output logic full_o,
  output logic empty_o,
  // Current depth of the FIFO, i.e., number of entries the FIFO currently contains.
  // Value range: [0, Depth]
  output logic [DepthW-1:0] depth_o,
  output logic err_o
);

  // Internal 'wrap' pointers that have an extra leading bit to account for wraparounds.
  localparam int unsigned WrapPtrW = PtrW + 1;
  logic [WrapPtrW-1:0] wptr_wrap_cnt_q, wptr_wrap_set_cnt,
                       rptr_wrap_cnt_q, rptr_wrap_set_cnt;

  // Derive real read and write pointers by truncating the internal 'wrap' pointers.
  assign wptr_o = wptr_wrap_cnt_q[PtrW-1:0];
  assign rptr_o = rptr_wrap_cnt_q[PtrW-1:0];

  // Extract the MSB of the 'wrap' pointers.
  logic wptr_wrap_msb, rptr_wrap_msb;
  assign wptr_wrap_msb = wptr_wrap_cnt_q[WrapPtrW-1];
  assign rptr_wrap_msb = rptr_wrap_cnt_q[WrapPtrW-1];

  // Wrap pointers when they have reached the maximum value and are about to get incremented.
  logic wptr_wrap_set, rptr_wrap_set;
  assign wptr_wrap_set = incr_wptr_i & (wptr_o == PtrW'(Depth));
  assign rptr_wrap_set = incr_rptr_i & (rptr_o == PtrW'(Depth-1));

  // When wrapping, invert the MSB and reset all lower bits to zero.
  assign wptr_wrap_set_cnt = {~wptr_wrap_msb, {(WrapPtrW-1){1'b0}}};
  assign rptr_wrap_set_cnt = {~rptr_wrap_msb, {(WrapPtrW-1){1'b0}}};

  // Full when both 'wrap' counters have a different MSB but all lower bits are equal.
  assign full_o = wptr_wrap_cnt_q == (rptr_wrap_cnt_q ^ {1'b1, {(WrapPtrW-1){1'b0}}});
  // Empty when both 'wrap' counters are equal in all bits including the MSB.
  assign empty_o = wptr_wrap_cnt_q == rptr_wrap_cnt_q;

  // The current depth is equal to:
  // - when full: the maximum depth;
  // - when both or none of the 'wrap' pointers are wrapped: the difference of the real pointers;
  // - when only one of the two 'wrap' pointers is wrapped: the maximum depth minus the difference
  //   of the real pointers.
  assign depth_o = full_o                         ? DepthW'(Depth) :
                   wptr_wrap_msb == rptr_wrap_msb ? DepthW'(wptr_o) - DepthW'(rptr_o) :
                   DepthW'(Depth) - DepthW'(rptr_o) + DepthW'(wptr_o);

  if (Secure) begin : gen_secure_ptrs
    logic wptr_err;
    prim_count #(
      .Width(WrapPtrW),
      .PossibleActions((NeverClears ? 0 : 4'h1) |
                       4'h2 | 4'h4)
    ) u_wptr (
      .clk_i,
      .rst_ni,
      .clr_i,
      .set_i(wptr_wrap_set),
      .set_cnt_i(wptr_wrap_set_cnt),
      .incr_en_i(incr_wptr_i),
      .decr_en_i(1'b0),
      .step_i(WrapPtrW'(1'b1)),
      .commit_i(1'b1),
      .cnt_o(wptr_wrap_cnt_q),
      .cnt_after_commit_o(),
      .err_o(wptr_err)
    );

    logic rptr_err;
    prim_count #(
      .Width(WrapPtrW),
      .PossibleActions((NeverClears ? 0 : 4'h1) |
                       4'h2 | 4'h4)
    ) u_rptr (
      .clk_i,
      .rst_ni,
      .clr_i,
      .set_i(rptr_wrap_set),
      .set_cnt_i(rptr_wrap_set_cnt),
      .incr_en_i(incr_rptr_i),
      .decr_en_i(1'b0),
      .step_i(WrapPtrW'(1'b1)),
      .commit_i(1'b1),
      .cnt_o(rptr_wrap_cnt_q),
      .cnt_after_commit_o(),
      .err_o(rptr_err)
    );

    assign err_o = wptr_err | rptr_err;

  end else begin : gen_normal_ptrs
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        wptr_wrap_cnt_q <= {WrapPtrW{1'b0}};
      end else if (clr_i) begin
        wptr_wrap_cnt_q <= {WrapPtrW{1'b0}};
      end else if (wptr_wrap_set) begin
        wptr_wrap_cnt_q <= wptr_wrap_set_cnt;
      end else if (incr_wptr_i) begin
        wptr_wrap_cnt_q <= wptr_wrap_cnt_q + {{(WrapPtrW-1){1'b0}}, 1'b1};
      end
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        rptr_wrap_cnt_q <= {WrapPtrW{1'b0}};
      end else if (clr_i) begin
        rptr_wrap_cnt_q <= {WrapPtrW{1'b0}};
      end else if (rptr_wrap_set) begin
        rptr_wrap_cnt_q <= rptr_wrap_set_cnt;
      end else if (incr_rptr_i) begin
        rptr_wrap_cnt_q <= rptr_wrap_cnt_q + {{(WrapPtrW-1){1'b0}}, 1'b1};
      end
    end

    assign err_o = '0;
  end

  if (NeverClears) begin : gen_never_clears
    `ASSERT(NeverClears_A, !clr_i)
  end

endmodule // prim_fifo_sync_cnt
