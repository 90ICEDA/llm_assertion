#!/bin/sh
set -eu
cd "/mnt/d/AssertionForge-main1/deliverables/obligation_completion_audit_20261013_r01/replays/stat_overlap"
"iverilog" "-g2012" "-s" "tb" "-I" "/mnt/d/AssertionForge-main1/deliverables/obligation_evidence_20261013_r02/frozen/stat" "-I" "/mnt/d/AssertionForge-main1/external/common_cells/include" "-o" "sim.out" "rtl.v" "checker_tb.sv"
vvp sim.out
