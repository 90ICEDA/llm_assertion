#!/usr/bin/env python3
"""Finalize contract assets for the common_cells scale210 cases."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "rtl_cases_real_scale210_independent"

CONTRACTS = {
410: ("A request launched by edge_i is retained across the transmit/receive clock boundary until acknowledgement. Reset in either domain clears the corresponding observable handshake state; no receive pulse or transmit acknowledgement is emitted solely because reset was asserted.",
      "assert property (@(posedge clk_tx_i) !rst_tx_ni |-> !ack_tx_o);", ["clk_tx_i","rst_tx_ni","edge_i","ack_tx_o","clk_rx_i","rst_rx_ni","edge_o"]),
411: ("The receive-domain synchronizer is cleared by receive reset. After reset, edge_o remains low until a new request has propagated from edge_i through the clock-domain crossing.",
      "assert property (@(posedge clk_rx_i) !rst_rx_ni |-> !edge_o);", ["clk_rx_i","rst_rx_ni","edge_i","edge_o","clk_tx_i","rst_tx_ni","ack_tx_o"]),
412: ("Reset clears the retained input request and synchronizer state. With reset asserted, valid_o is low and the exposed retained-request and synchronization aliases are zero.",
      "assert property (@(posedge clk_i) !rst_ni |-> (!valid_o && !r_input_reg && sync_a == 2'b00));", ["clk_i","rst_ni","valid_i","ack_i","valid_o","r_input_reg","sync_a[1:0]"]),
413: ("Reset clears both stages of the exposed synchronizer state. No valid output may be reported while reset is asserted.",
      "assert property (@(posedge clk_i) !rst_ni |-> (!valid_o && sync_a == 2'b00));", ["clk_i","rst_ni","valid_i","ack_i","valid_o","sync_a[1:0]"]),
414: ("An unacknowledged valid input is retained across cycles. Once accepted into the retained-request state, it remains visible until acknowledgement permits the protocol to advance.",
      "assert property (@(posedge clk_i) disable iff (!rst_ni) (valid_i && !ack_i) |=> r_input_reg);", ["clk_i","rst_ni","valid_i","ack_i","valid_o","r_input_reg","sync_a[1:0]"]),
415: ("Assertion of the selected functional reset forces rst_no and init_no low, independent of earlier state. Reset outputs may only begin release after the selected reset input is released.",
      "assert property (@(posedge clk_i) !rst_ni |-> (!rst_no && !init_no));", ["clk_i","rst_ni","rst_test_mode_ni","test_mode_i","rst_no","init_no"]),
416: ("After the selected reset input is released, the reset synchronizer advances on successive clk_i edges and eventually releases rst_no and init_no; they must not remain low indefinitely.",
      "assert property (@(posedge clk_i) disable iff (!rst_ni) $rose(rst_ni) |-> ##[1:5] (rst_no && init_no));", ["clk_i","rst_ni","rst_test_mode_ni","test_mode_i","rst_no","init_no"]),
417: ("While asynchronous reset is asserted, clk_o is held inactive. Following reset release, the selected functional clock may propagate only after the bypass-control state has been safely established.",
      "assert property (@(negedge async_rstn_i) !async_rstn_i |-> !clk_o);", ["async_rstn_i","async_sel_i","clks_i[1:0]","test_clk_i","test_en_i","clk_o"]),
418: ("Reasserting asynchronous reset disables clock propagation promptly: clk_o is low during reset and does not retain a previously selected clock transition.",
      "assert property (@(negedge async_rstn_i) !async_rstn_i |-> !clk_o);", ["async_rstn_i","async_sel_i","clks_i[1:0]","test_clk_i","test_en_i","clk_o"]),
419: ("Reset closes the integral-divider output gate. At a sampled clk_i edge with reset asserted, the exposed gate-open state and clk_o are low.",
      "assert property (@(posedge clk_i) !rst_ni |-> (!gate_is_open_q && !clk_o));", ["clk_i","rst_ni","en_i","test_mode_en_i","div_i[3:0]","div_valid_i","div_ready_o","gate_en_q","gate_is_open_q","clk_o","cycl_count_o[3:0]"]),
420: ("Outside reset and test bypass, the divider gate-open state follows the prior cycle's gate enable qualified by en_i. This state controls whether divided clock activity is allowed.",
      "assert property (@(posedge clk_i) disable iff (!rst_ni) !test_mode_en_i |=> (gate_is_open_q == $past(gate_en_q && en_i)));", ["clk_i","rst_ni","en_i","test_mode_en_i","div_i[3:0]","div_valid_i","div_ready_o","gate_en_q","gate_is_open_q","clk_o","cycl_count_o[3:0]"]),
437: ("usage_o reports the current FIFO occupancy. A successful push into an empty FIFO without a simultaneous pop increases the reported usage on the next clock edge.",
      "assert property (@(posedge clk_i) disable iff (!rst_ni) (push_i && !pop_i && empty_o) |=> (usage_o != 0));", ["clk_i","rst_ni","push_i","pop_i","flush_i","clr_i","empty_o","full_o","usage_o[1:0]","data_i[7:0]","data_o[7:0]"]),
438: ("For the zero-depth FIFO configuration, emptiness is the inverse of an active push in the same cycle; a presented item makes the combinational FIFO non-empty.",
      "assert property (@(*) (empty_o == !push_i));", ["push_i","empty_o","full_o","data_i[7:0]","data_o[7:0]"]),
439: ("For a one-bit input, is_onehot_o is true exactly when d_i is one and false when d_i is zero.",
      "assert property (@(*) (is_onehot_o == d_i));", ["d_i","is_onehot_o"]),
440: ("is_onehot_o is asserted exactly when the four-bit input contains one and only one asserted bit.",
      "assert property (@(*) (is_onehot_o == $onehot(d_i)));", ["d_i[3:0]","is_onehot_o"]),
441: ("The mux output data equals the data lane selected by inp_sel_i in the same cycle, independently of activity on unselected lanes.",
      "assert property (@(*) (oup_data_o == inp_data_i[inp_sel_i*8 +: 8]));", ["inp_data_i[23:0]","inp_valid_i[2:0]","inp_ready_o[2:0]","inp_sel_i[1:0]","oup_data_o[7:0]","oup_valid_o","oup_ready_i"]),
442: ("The mux output valid equals the valid bit of the selected input lane in the same cycle. Backpressure is returned only to the selected lane.",
      "assert property (@(*) (oup_valid_o == inp_valid_i[inp_sel_i]));", ["inp_data_i[23:0]","inp_valid_i[2:0]","inp_ready_o[2:0]","inp_sel_i[1:0]","oup_data_o[7:0]","oup_valid_o","oup_ready_i"]),
443: ("For the one-bit leading-zero counter, cnt_o is one for input zero and zero for input one; empty_o identifies the all-zero input.",
      "assert property (@(*) (cnt_o == !in_i && empty_o == !in_i));", ["in_i","cnt_o","empty_o"]),
444: ("empty_o is asserted exactly when the one-bit input is zero.",
      "assert property (@(*) (empty_o == !in_i));", ["in_i","cnt_o","empty_o"]),
}

VARIANTS = {
    "primary": ("waveform_good.csv", "waveform_bad.csv"),
    "heldout": ("waveform_good_holdout.csv", "waveform_bad_holdout.csv"),
    "decoy": ("waveform_good_decoy.csv", "waveform_bad_decoy.csv"),
}

def first_divergence(case: Path, good_name: str, bad_name: str) -> dict:
    with (case / good_name).open(newline="", encoding="utf-8") as f:
        good = list(csv.DictReader(f))
    with (case / bad_name).open(newline="", encoding="utf-8") as f:
        bad = list(csv.DictReader(f))
    if len(good) != len(bad):
        raise ValueError(f"row-count mismatch in {case.name}: {good_name}/{bad_name}")
    fields = [x for x in (good[0].keys() if good else []) if x != "time_ps"]
    for idx, (g, b) in enumerate(zip(good, bad)):
        changed = [s for s in fields if g.get(s) != b.get(s)]
        if changed:
            return {
                "time_ps": int(g["time_ps"]), "observation_index": idx,
                "signals": changed,
                "good": {s: g[s] for s in changed},
                "bad": {s: b[s] for s in changed},
            }
    raise ValueError(f"no divergence in {case.name}: {good_name}/{bad_name}")

def main() -> None:
    completed = []
    for number, (spec, sva, relevant) in CONTRACTS.items():
        matches = list(ROOT.glob(f"case{number}_*"))
        if len(matches) != 1:
            raise RuntimeError(f"expected one case{number}, got {len(matches)}")
        case = matches[0]
        metadata_path = case / "case_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_project") != "common_cells":
            raise ValueError(f"unexpected project for {case.name}")
        temporal_type = metadata["temporal_type"]
        metadata["spec"] = spec
        metadata["golden_sva"] = {"sva": sva, "temporal_type": temporal_type}
        metadata["first_divergence"] = {
            role: first_divergence(case, good, bad)
            for role, (good, bad) in VARIANTS.items()
        }
        metadata["relevant_signals"] = relevant
        metadata["contract_status"] = "formal_complete"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (case / "spec.md").write_text(
            f"# Behavioral specification\n\n{spec}\n\n"
            f"Temporal type: `{temporal_type}`\n", encoding="utf-8")
        (case / "golden.sva").write_text(
            f"// Temporal type: {temporal_type}\n{sva}\n", encoding="utf-8")
        completed.append(case.name)
    print(json.dumps({"completed": len(completed), "cases": completed}, indent=2))

if __name__ == "__main__":
    main()
