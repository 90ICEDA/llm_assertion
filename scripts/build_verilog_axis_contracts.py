#!/usr/bin/env python3
"""Materialize behavioral contracts for the scale210 verilog-axis cases.

This script is intentionally read-only with respect to RTL, testbenches, and
waveforms.  It updates only case_metadata.json, spec.md, and golden.sva.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "rtl_cases_real_scale210_independent"
VARIANTS = (("primary", ""), ("heldout", "_holdout"), ("decoy", "_decoy"))

CONTRACTS = {
421: ("After reset is released, an idle output with downstream ready must cause the registered source-ready output to assert on the next clock. Accepted source beats must subsequently obey ready/valid backpressure.",
      "assert property (@(posedge clk) disable iff (rst) (m_axis_tready && !m_axis_tvalid) |=> s_axis_tready);", "one-cycle registered readiness", ["clk", "rst", "s_axis_tready", "m_axis_tvalid", "m_axis_tready"]),
422: ("A source beat accepted while the output path can advance must make output valid on the following clock and preserve the accepted payload until the downstream handshake.",
      "assert property (@(posedge clk) disable iff (rst) (s_axis_tvalid && s_axis_tready && m_axis_tready) |=> m_axis_tvalid);", "one-cycle valid propagation", ["clk", "rst", "s_axis_tvalid", "s_axis_tready", "s_axis_tdata", "m_axis_tvalid", "m_axis_tready", "m_axis_tdata"]),
423: ("When a second source beat is accepted while a prior output beat is stalled, backpressure must be asserted once the temporary capacity is occupied; both accepted beats must remain available in order as downstream readiness returns.",
      "assert property (@(posedge clk) disable iff (rst) (m_axis_tvalid && !m_axis_tready && s_axis_tvalid && s_axis_tready) |=> !s_axis_tready);", "skid-buffer occupancy across backpressure", ["clk", "rst", "s_axis_tvalid", "s_axis_tready", "s_axis_tdata", "m_axis_tvalid", "m_axis_tready", "m_axis_tdata"]),
424: ("The overflow status is a pulse: after it is asserted for an oversized or dropped frame, it must return low on the next clock unless a new overflow event is reported.",
      "assert property (@(posedge clk) disable iff (rst) status_overflow |=> !status_overflow);", "one-cycle status pulse", ["clk", "rst", "s_axis_tvalid", "s_axis_tready", "s_axis_tlast", "status_overflow"]),
425: ("Completing a frame marked bad must produce a one-clock bad-frame status pulse; in the absence of another completed bad frame, the indication must clear on the following clock.",
      "assert property (@(posedge clk) disable iff (rst) status_bad_frame |=> !status_bad_frame);", "one-cycle bad-frame pulse", ["clk", "rst", "s_axis_tvalid", "s_axis_tready", "s_axis_tlast", "s_axis_tuser", "status_bad_frame"]),
426: ("Completing a frame not marked bad must produce a one-clock good-frame status pulse; in the absence of another completed good frame, the indication must clear on the following clock.",
      "assert property (@(posedge clk) disable iff (rst) status_good_frame |=> !status_good_frame);", "one-cycle good-frame pulse", ["clk", "rst", "s_axis_tvalid", "s_axis_tready", "s_axis_tlast", "s_axis_tuser", "status_good_frame"]),
427: ("When at least one request is pending after reset, the arbiter must publish a one-hot grant for an eligible requester; a granted request remains governed by acknowledge and arbitration policy.",
      "assert property (@(posedge clk) disable iff (rst) ((|request) && !(|grant)) |=> (|grant));", "registered grant acquisition", ["clk", "rst", "request", "acknowledge", "grant", "grant_valid", "grant_encoded"]),
428: ("When a pending request is selected, the arbiter must assert grant-valid together with the corresponding grant indication on the registered arbitration result.",
      "assert property (@(posedge clk) disable iff (rst) ((|request) && !grant_valid) |=> grant_valid);", "registered grant-valid acquisition", ["clk", "rst", "request", "acknowledge", "grant", "grant_valid", "grant_encoded"]),
429: ("In rate-limited operation outside an active frame, sustained valid traffic must consume the configured allowance and apply source backpressure when the allowance is exhausted; forwarding resumes as the accumulator recovers.",
      "assert property (@(posedge clk) disable iff (rst) (!by_frame && s_axis_tvalid && s_axis_tready) |-> ##[1:$] !s_axis_tready);", "multi-cycle rate-limit accumulation", ["clk", "rst", "by_frame", "s_axis_tvalid", "s_axis_tready", "m_axis_tvalid", "m_axis_tready"]),
430: ("With frame-aware limiting enabled, once the first beat of a frame is accepted, an idle gap before the final beat must not cause that continuing frame to be treated as a new frame or spuriously backpressured.",
      "assert property (@(posedge clk) disable iff (rst) (by_frame && s_axis_tvalid && s_axis_tready && !s_axis_tlast) ##1 !s_axis_tvalid |=> s_axis_tready);", "frame state across an inter-beat gap", ["clk", "rst", "by_frame", "s_axis_tvalid", "s_axis_tready", "s_axis_tlast", "m_axis_tvalid", "m_axis_tready"]),
445: ("The priority encoder must assert output-valid whenever at least one input bit is asserted, and must deassert it when the input vector is zero.",
      "assert property (@(input_unencoded) (|input_unencoded) |-> output_valid);", "combinational validity", ["input_unencoded", "output_valid"]),
446: ("For every nonzero input vector, the encoded output must identify the selected asserted input and the one-hot decoded output must agree with that encoded index.",
      "assert property (@(input_unencoded) output_valid |-> (output_unencoded == (1'b1 << output_encoded)) && input_unencoded[output_encoded]);", "combinational priority encoding", ["input_unencoded", "output_valid", "output_encoded", "output_unencoded"]),
447: ("When routing is enabled and the downstream output can accept a beat, ready must be returned only on the currently selected source lane.",
      "assert property (@(posedge clk) disable iff (rst) (enable && m_axis_tready) |-> s_axis_tready[select]);", "selected-lane ready propagation", ["clk", "rst", "enable", "select", "s_axis_tvalid", "s_axis_tready", "m_axis_tready"]),
448: ("A valid beat accepted from the selected source must emerge with the same payload on the multiplexed output and remain stable whenever the output is stalled.",
      "assert property (@(posedge clk) disable iff (rst) (m_axis_tvalid && m_axis_tready) |-> (m_axis_tdata == s_axis_tdata[select*DATA_WIDTH +: DATA_WIDTH]));", "selected payload preservation", ["clk", "rst", "enable", "select", "s_axis_tdata", "s_axis_tvalid", "s_axis_tready", "m_axis_tdata", "m_axis_tvalid", "m_axis_tready"]),
449: ("When routing is enabled without dropping and the selected destination has capacity, source-ready must assert; disabled or dropped routing must not falsely acknowledge a source transfer.",
      "assert property (@(posedge clk) disable iff (rst) (enable && !drop && m_axis_tready[select] && !(|m_axis_tvalid)) |=> s_axis_tready);", "registered demultiplexer readiness", ["clk", "rst", "enable", "drop", "select", "s_axis_tvalid", "s_axis_tready", "m_axis_tready", "m_axis_tvalid"]),
450: ("An accepted source beat must be delivered only to the selected destination with its payload preserved; all unselected destination-valid bits must remain low.",
      "assert property (@(posedge clk) disable iff (rst) m_axis_tvalid[select] |-> (m_axis_tdata[select*DATA_WIDTH +: DATA_WIDTH] == s_axis_tdata));", "demultiplexed payload preservation", ["clk", "rst", "enable", "drop", "select", "s_axis_tdata", "s_axis_tvalid", "s_axis_tready", "m_axis_tdata", "m_axis_tvalid", "m_axis_tready"]),
}


def first_divergence(case_dir: Path, suffix: str) -> dict:
    with (case_dir / f"waveform_good{suffix}.csv").open(newline="") as f:
        good = list(csv.DictReader(f))
    with (case_dir / f"waveform_bad{suffix}.csv").open(newline="") as f:
        bad = list(csv.DictReader(f))
    previous_clk = "0"
    rising_edges = 0
    for index, (g, b) in enumerate(zip(good, bad)):
        clk = g.get("clk")
        if clk is not None and previous_clk != "1" and clk == "1":
            rising_edges += 1
        if clk is not None:
            previous_clk = clk
        signals = [key for key in g if key != "time_ps" and g[key] != b.get(key)]
        if signals:
            out = {"time_ps": int(g["time_ps"]), "sample_index": index, "signals": signals}
            if clk is not None:
                out["clock_cycle"] = rising_edges
            return out
    raise RuntimeError(f"no good/bad divergence for {case_dir.name}{suffix}")


def main() -> None:
    for number, (spec, sva, temporal_type, relevant) in CONTRACTS.items():
        matches = list(ROOT.glob(f"case{number}_*"))
        if len(matches) != 1:
            raise RuntimeError(f"expected one directory for case{number}, got {matches}")
        case_dir = matches[0]
        metadata_path = case_dir / "case_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["spec"] = spec
        metadata["golden_sva"] = {"sva": sva, "temporal_type": temporal_type}
        metadata["first_divergence"] = {
            label: first_divergence(case_dir, suffix) for label, suffix in VARIANTS
        }
        metadata["relevant_signals"] = relevant
        metadata["temporal_type"] = temporal_type
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        (case_dir / "spec.md").write_text(
            f"# Behavioral specification\n\n{spec}\n", encoding="utf-8"
        )
        (case_dir / "golden.sva").write_text(
            f"// Temporal type: {temporal_type}\n{sva}\n", encoding="utf-8"
        )
        print(case_dir.name)


if __name__ == "__main__":
    main()
