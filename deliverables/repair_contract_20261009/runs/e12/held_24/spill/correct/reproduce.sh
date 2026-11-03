#!/bin/sh
set -eu
cd /mnt/d/AssertionForge-main1/deliverables/repair_contract_20261009/runs/e12/held_24/spill/correct
iverilog -g2012 -s tb -I /mnt/d/AssertionForge-main1/rtl_cases_real_scale210_independent_next/case510_cc_spill_register_flush_push_priority -I /mnt/d/AssertionForge-main1/external/common_cells/include -o sim.out rtl.v checker_tb.sv
vvp sim.out
