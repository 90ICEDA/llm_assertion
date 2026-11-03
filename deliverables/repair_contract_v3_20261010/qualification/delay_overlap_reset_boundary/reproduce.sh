#!/bin/sh
set -eu
cd /mnt/d/AssertionForge-main1/deliverables/repair_contract_v3_20261010/qualification/delay_overlap_reset_boundary
iverilog -g2012 -s tb -o sim.out checker_tb.sv
vvp sim.out
