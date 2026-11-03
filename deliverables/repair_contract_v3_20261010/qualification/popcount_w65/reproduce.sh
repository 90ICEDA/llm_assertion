#!/bin/sh
set -eu
cd /mnt/d/AssertionForge-main1/deliverables/repair_contract_v3_20261010/qualification/popcount_w65
iverilog -g2012 -s tb -o sim.out checker_tb.sv
vvp sim.out
