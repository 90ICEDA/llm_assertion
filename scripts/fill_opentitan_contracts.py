#!/usr/bin/env python3
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "rtl_cases_real_scale210_independent"

CONTRACTS = {
401: ("While reset is asserted, the filter's retained output state is cleared to zero. After reset release, disabled filtering passes filter_i directly; enabled filtering changes filter_o only after the sampled input has remained consistently opposite for the configured filter length.", "FilterReset_A", "assert property (@(posedge clk_i) (!rst_ni) |-> (stored_value_q == 1'b0));", "reset state initialization", ["rst_ni","clk_i","enable_i","filter_i","filter_o","stored_value_q"]),
402: ("With filtering enabled, once the input has held one polarity for the configured filter length, the retained value and filter_o adopt that polarity and remain there until an equally qualified opposite input is observed.", "QualifiedInputUpdates_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && (&stored_vector_q)) |=> (stored_value_q && filter_o));", "qualified multi-cycle update", ["rst_ni","clk_i","enable_i","filter_i","filter_o","stored_value_q","stored_vector_q"]),
403: ("Reset clears the complete input-history vector. On each active clock after reset, the history shifts by one sample and appends filter_i, providing the configured observation window used by the filter.", "HistoryReset_A", "assert property (@(posedge clk_i) (!rst_ni) |-> (stored_vector_q == '0));", "reset state initialization", ["rst_ni","clk_i","filter_i","stored_vector_q"]),
404: ("Reset drives the registered interrupt output low. Outside reset, the interrupt output is the previous clock's enabled interrupt status, preserving the module's registered-output timing.", "InterruptReset_A", "assert property (@(posedge clk_i) (!rst_ni) |-> (intr_o == '0));", "reset state initialization", ["rst_ni","clk_i","event_intr_i","reg2hw_intr_enable_q_i","reg2hw_intr_state_q_i","intr_o"]),
405: ("For the registered-output configuration, every active clock captures the enabled interrupt status into intr_o; a newly asserted enabled status therefore appears on intr_o on the following sampled cycle.", "EnabledStatusRegisters_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |=> intr_o);", "one-cycle registered response", ["rst_ni","clk_i","reg2hw_intr_enable_q_i","reg2hw_intr_state_q_i","intr_o"]),
406: ("Reset initializes the FIFO write pointer and occupancy to zero, making the FIFO empty and not full before any accepted pointer increment.", "FifoReset_A", "assert property (@(posedge clk_i) (!rst_ni) |-> ((wptr_o == '0) && (depth_o == '0) && empty_o && !full_o));", "reset state initialization", ["rst_ni","clk_i","wptr_o","depth_o","empty_o","full_o"]),
407: ("When clr_i is sampled high, both FIFO pointer state and the reported occupancy return to zero on the following sampled cycle, with empty asserted.", "FifoClear_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) clr_i |=> ((wptr_o == '0) && (depth_o == '0) && empty_o));", "one-cycle synchronous clear", ["rst_ni","clk_i","clr_i","wptr_o","rptr_o","depth_o","empty_o"]),
408: ("An accepted write advances wptr_o modulo the configured depth. A write accepted at the final pointer position wraps wptr_o to zero on the following sampled cycle while occupancy accounting continues across the wrap.", "WritePointerWraps_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) (incr_wptr_i && (wptr_o == 2'd3)) |=> (wptr_o == 2'd0));", "one-cycle delayed state transition", ["rst_ni","clk_i","clr_i","incr_wptr_i","wptr_o","depth_o","full_o","empty_o"]),
409: ("Each accepted write-pointer increment advances wptr_o by one modulo the configured depth on the following sampled cycle, unless clear is active.", "WritePointerAdvances_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) (incr_wptr_i && !clr_i) |=> (wptr_o == ($past(wptr_o) + 1'b1)));", "one-cycle delayed state transition", ["rst_ni","clk_i","clr_i","incr_wptr_i","wptr_o","depth_o","empty_o","full_o"]),
431: ("With checking enabled, an input vector containing exactly one asserted bit is a valid one-hot code and must not raise err_o; zero-hot and multi-hot values are rejected according to the configured check mode.", "ValidOneHotAccepted_A", "assert property (@(oh_i or rst_ni) disable iff (!rst_ni) $onehot(oh_i) |-> !err_o);", "same-cycle protocol validation", ["rst_ni","oh_i","err_o"]),
432: ("With checking enabled and address checking selected, a one-hot input whose asserted-bit index equals addr_i is valid and must not raise err_o.", "MatchingOneHotAddressAccepted_A", "assert property (@(oh_i or addr_i or en_i or rst_ni) disable iff (!rst_ni) (en_i && $onehot(oh_i) && oh_i[addr_i]) |-> !err_o);", "same-cycle protocol validation", ["rst_ni","en_i","oh_i","addr_i","err_o"]),
433: ("In the no-synchronizer configuration, q_sync_o follows d_i without an added cycle. A sampled rising or falling transition is also reported by the corresponding one-cycle edge pulse.", "UnsynchronizedPathTracks_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) (q_sync_o == d_i));", "same-cycle signal propagation", ["rst_ni","clk_i","d_i","q_sync_o","q_posedge_pulse_o","q_negedge_pulse_o"]),
434: ("In the no-synchronizer configuration, q_sync_o continuously reflects d_i; edge pulse outputs describe transitions between the current synchronized value and its prior sampled value.", "SynchronizedOutputTracks_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) (q_sync_o == d_i));", "same-cycle signal propagation", ["rst_ni","clk_i","d_i","q_sync_o","q_posedge_pulse_o","q_negedge_pulse_o"]),
435: ("When filtering is disabled, filter_o is a transparent view of filter_i. When filtering is enabled, output changes are qualified by the threshold counter rather than bypassing the filter.", "DisabledFilterBypasses_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));", "same-cycle bypass behavior", ["rst_ni","clk_i","enable_i","filter_i","filter_o","thresh_i"]),
436: ("With filtering enabled, an input that remains at one polarity for the full counter qualification interval is eventually committed to filter_o; shorter disturbances do not change the retained output.", "PersistentInputCommits_A", "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && $stable(filter_i))[*4] |-> (filter_o == filter_i));", "multi-cycle persistence qualification", ["rst_ni","clk_i","enable_i","filter_i","filter_o","thresh_i"]),
}

def divergence(case_dir, suffix):
    good = list(csv.DictReader(open(case_dir / f"waveform_good{suffix}.csv", newline="")))
    bad = list(csv.DictReader(open(case_dir / f"waveform_bad{suffix}.csv", newline="")))
    rising = -1
    prev_clk = "0"
    for idx, (g, b) in enumerate(zip(good, bad)):
        clk = g.get("clk_i", "0")
        if clk == "1" and prev_clk != "1": rising += 1
        prev_clk = clk
        sigs = [k for k in g if k not in ("time_ps", "cycle", "time") and g[k] != b[k]]
        if sigs:
            return {"time_ps": int(g["time_ps"]), "cycle_index": rising if rising >= 0 else None,
                    "sample_index": idx, "clock_phase": ("rising edge" if clk == "1" else "between rising edges") if rising >= 0 else "combinational sample",
                    "signals": sigs, "good_values": {s:g[s] for s in sigs},
                    "bad_values": {s:b[s] for s in sigs}}
    raise RuntimeError(f"no divergence: {case_dir.name}{suffix}")

for number, (spec, name, sva, temporal_type, relevant) in CONTRACTS.items():
    case_dir = next(ROOT.glob(f"case{number}_*"))
    path = case_dir / "case_metadata.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["spec"] = spec
    event = sva[sva.index("@("):sva.index(")", sva.index("@("))+1]
    meta["golden_sva"] = {"name": name, "clock": event,
        "disable_iff": None if "(!rst_ni) |->" in sva else "!rst_ni",
        "sva": sva, "assertion": sva, "temporal_type": temporal_type}
    meta["first_divergence"] = {
        "cycle_definition": "cycle_index is the zero-based ordinal of the rising clk_i edge; sample_index is the zero-based CSV data-row index",
        "primary": divergence(case_dir, ""), "heldout": divergence(case_dir, "_holdout"),
        "decoy": divergence(case_dir, "_decoy")}
    meta["relevant_signals"] = relevant
    meta["status"] = "trace_validated_metadata_complete"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (case_dir / "spec.md").write_text(f"# Behavioral specification\n\n{spec}\n", encoding="utf-8")
    (case_dir / "golden.sva").write_text(f"// {name}\n{sva}\n", encoding="utf-8")
    print(case_dir.name)
