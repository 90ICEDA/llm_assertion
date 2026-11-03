#!/bin/sh
set -eu
cd /mnt/d/AssertionForge-main1/deliverables/obligation_continuation_20261013_r01/runs/final_examples/fifo_B/fifo/buggy
iverilog -g2012 -s tb -I /mnt/d/AssertionForge-main1/deliverables/obligation_continuation_20261013_r01/formal/quarantine/fifo -I /mnt/d/AssertionForge-main1/external/common_cells/include -o sim.out rtl.v checker_tb.sv
vvp sim.out
