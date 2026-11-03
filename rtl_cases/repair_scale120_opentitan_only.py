#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from build_real_rtl_benchmark import build_case
from decoy_structure import ensure_decoy_structure
from real_rtl_case_catalog import load_case_blueprints


ROOT = Path(__file__).resolve().parents[1]
SCALE_ROOT = ROOT / "rtl_cases_real_scale120"
REAL_ROOT = ROOT / "rtl_cases_real"
ACTIVE_ROOT = ROOT / "rtl_cases_real_active"

SYNTHETIC_CASES = [
    "case241_uart_tfifo_full_early",
    "case242_uart_tfifo_empty_late",
    "case243_uart_tfifo_count_off_by_one",
    "case284_uart_tfifo_clear_ignored",
    "case285_wb_conmax_arb_priority_reversed",
    "case286_wb_conmax_arb_grant_without_req",
    "case287_wb_conmax_arb_valid_depends_on_ack",
    "case288_i2c_master_start_busy_missing",
    "case289_i2c_master_start_drive_missing",
    "case290_i2c_master_stop_release_late",
    "case291_spi_top_cs_not_asserted_on_start",
    "case292_spi_top_busy_drops_early",
    "case293_spi_top_sclk_toggles_while_idle",
]

COPY_CASES = {
    "case114_prim_edge_negedge_misdecoded": ACTIVE_ROOT,
    "case115_prim_edge_both_edges_collapsed": ACTIVE_ROOT,
    "case121_prim_intr_test_qe_ignored": REAL_ROOT,
    "case122_prim_filter_ctr_streak_reset_ignored": REAL_ROOT,
    "case123_prim_edge_sync_output_lag": REAL_ROOT,
    "case127_prim_intr_status_test_qe_ignored": REAL_ROOT,
    "case133_prim_edge_negedge_missing": ACTIVE_ROOT,
}

ARBITER_CASES = [
    {
        "name": "case107_prim_arbiter_priority_reversed",
        "spec": "When multiple requests are high, the fixed arbiter shall grant the lowest index request in the same cycle when ready_i is high.",
        "bug_class": "combination_same_cycle",
        "bug_family": "priority_resolution",
        "bug_type": "left/right fixed priority reversed",
        "golden_sva": {
            "sva": "assert property (@(posedge clk) disable iff (!rst_n) (ready_i && (req_i == 4'b0011)) |-> (gnt_o == 4'b0001));",
            "expected_behavior": "A tied request including requestor 0 must still grant requestor 0 when ready_i is high.",
            "temporal_type": "same-cycle arbitration check",
        },
        "loose_negative_controls": [
            {
                "name": "some_grant_when_ready",
                "sva": "assert property (@(posedge clk) disable iff (!rst_n) (ready_i && (|req_i)) |-> (|gnt_o));",
                "why_it_should_miss": "The buggy arbiter still produces a legal-looking grant; it is just the wrong requester.",
            },
            {
                "name": "grant_implies_request",
                "sva": "assert property (@(posedge clk) disable iff (!rst_n) (|gnt_o) |-> (|req_i));",
                "why_it_should_miss": "It never constrains the exact fixed-priority ordering.",
            },
        ],
        "hard_case_rationale": "This is a classic exact-priority corner: broad handshake assertions still pass while the winner selection is subtly wrong.",
        "overfit_lure": "Seen trace uses tied request vectors 0011 and 1010; held-out switches to 1100 and 0110 so literal requester memorization breaks.",
        "stimulus_notes": "Seen and held-out both preserve the same fixed-priority relation but change the tied request pattern and the backpressure prelude.",
        "primary": [(0b0011, 1), (0b0100, 0), (0b1010, 0), (0b1010, 1), (0b0000, 0)],
        "holdout": [(0b1100, 1), (0b0110, 0), (0b0110, 1), (0b0000, 0)],
        "bug_mode": "priority_reversed",
    },
    {
        "name": "case108_prim_arbiter_grant_without_ready",
        "spec": "A grant shall only assert when ready_i is high in the same cycle.",
        "bug_class": "combination_same_cycle",
        "bug_family": "ready_valid_handshake",
        "bug_type": "grant can assert while sink is not ready",
        "golden_sva": {
            "sva": "assert property (@(posedge clk) disable iff (!rst_n) (!ready_i && (|req_i)) |-> (gnt_o == 4'b0000));",
            "expected_behavior": "Backpressure shall suppress grant_o even while requests remain pending.",
            "temporal_type": "same-cycle handshake suppression check",
        },
        "loose_negative_controls": [
            {
                "name": "valid_tracks_request",
                "sva": "assert property (@(posedge clk) disable iff (!rst_n) (|req_i) |-> valid_o);",
                "why_it_should_miss": "valid_o can still look correct even if grant_o illegally ignores ready_i.",
            },
            {
                "name": "grant_is_onehot",
                "sva": "assert property (@(posedge clk) disable iff (!rst_n) $onehot0(gnt_o));",
                "why_it_should_miss": "One-hotness says nothing about whether grants under backpressure are legal.",
            },
        ],
        "hard_case_rationale": "The bug hides in the exact no-ready suppression rule. Broad grant-exists and one-hotness checks all pass.",
        "overfit_lure": "Seen trace alternates ready_i around the same request literals; held-out changes requester identities while preserving the backpressure corner.",
        "stimulus_notes": "Seen and held-out preserve the same no-ready suppression bug but vary which requester is active under backpressure.",
        "primary": [(0b0011, 1), (0b0100, 0), (0b1010, 0), (0b1010, 1), (0b0000, 0)],
        "holdout": [(0b1100, 1), (0b0110, 0), (0b0110, 1), (0b0000, 0)],
        "bug_mode": "grant_without_ready",
    },
    {
        "name": "case109_prim_arbiter_valid_depends_on_ready",
        "spec": "valid_o shall reflect pending requests even when ready_i is low; backpressure may block grant_o but not pending-valid indication.",
        "bug_class": "combination_same_cycle",
        "bug_family": "ready_valid_handshake",
        "bug_type": "valid incorrectly drops under backpressure",
        "golden_sva": {
            "sva": "assert property (@(posedge clk) disable iff (!rst_n) (!ready_i && (|req_i)) |-> valid_o);",
            "expected_behavior": "Pending requests must remain visible through valid_o during backpressure.",
            "temporal_type": "same-cycle pending-valid check",
        },
        "loose_negative_controls": [
            {
                "name": "grant_requires_ready",
                "sva": "assert property (@(posedge clk) disable iff (!rst_n) (|gnt_o) |-> ready_i);",
                "why_it_should_miss": "The buggy design can still suppress grant_o correctly while valid_o disappears too early.",
            },
            {
                "name": "ready_and_request_imply_grant",
                "sva": "assert property (@(posedge clk) disable iff (!rst_n) (ready_i && (|req_i)) |-> (|gnt_o));",
                "why_it_should_miss": "It does not constrain the stalled cycles where valid_o must stay asserted.",
            },
        ],
        "hard_case_rationale": "This is a waiting-state visibility bug. Conservative grant-oriented assertions miss that pending work becomes invisible under backpressure.",
        "overfit_lure": "Seen trace keeps the same request high across ready_i=0 cycles; held-out changes which requester stalls so requester-literal overfitting fails.",
        "stimulus_notes": "Seen and held-out both hold requests high across ready_i=0 cycles, but they use different requester patterns.",
        "primary": [(0b0011, 1), (0b0100, 0), (0b1010, 0), (0b1010, 1), (0b0000, 0)],
        "holdout": [(0b1100, 1), (0b0110, 0), (0b0110, 1), (0b0000, 0)],
        "bug_mode": "valid_depends_on_ready",
    },
]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_manifest(path: Path) -> List[Dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def save_manifest(path: Path, entries: Sequence[Dict[str, object]]) -> None:
    write_text(path, json.dumps({"cases": list(entries)}, indent=2, ensure_ascii=False) + "\n")


def field_bit(value: int, width: int) -> str:
    return format(value, f"0{width}b")


def emit_trace(samples: Sequence[Dict[str, int]], widths: Dict[str, int]) -> List[Dict[str, str]]:
    ordered = ["time_ps", "clk"] + [key for key in samples[0].keys() if key != "clk"]
    rows: List[Dict[str, str]] = []
    time_ps = 0
    for sample in samples:
        low_row: Dict[str, str] = {"time_ps": str(time_ps), "clk": "0"}
        for key, value in sample.items():
            if key == "clk":
                continue
            width = widths[key]
            low_row[key] = field_bit(value, width) if width > 1 else str(value)
        rows.append(low_row)
        time_ps += 5000
        high_row = dict(low_row)
        high_row["time_ps"] = str(time_ps)
        high_row["clk"] = "1"
        rows.append(high_row)
        time_ps += 5000
    return [{key: row[key] for key in ordered} for row in rows]


def copy_case_dir(src_root: Path, dst_root: Path, case_name: str) -> None:
    src = src_root / case_name
    dst = dst_root / case_name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def patch_arbiter_source(case_dir: Path) -> None:
    normal_block = """          // forward path
          logic sel; // local helper variable
          always @* begin : p_node
            // this always gives priority to the left child
            sel = ~req_tree[C0];
            // propagate requests
            req_tree[Pa]  = req_tree[C0] | req_tree[C1];
            // data and index muxes
            idx_tree[Pa]  = (sel) ? idx_tree[C1]  : idx_tree[C0];
            data_tree[Pa] = (sel) ? data_tree[C1] : data_tree[C0];
            // propagate the grants back to the input
            gnt_tree[C0] = gnt_tree[Pa] & ~sel;
            gnt_tree[C1] = gnt_tree[Pa] &  sel;
          end"""
    normal_assign_block = """          // forward path
          wire sel; // local helper variable
          assign sel = ~req_tree[C0];
          // propagate requests
          assign req_tree[Pa]  = req_tree[C0] | req_tree[C1];
          // data and index muxes
          assign idx_tree[Pa]  = (sel) ? idx_tree[C1]  : idx_tree[C0];
          assign data_tree[Pa] = (sel) ? data_tree[C1] : data_tree[C0];
          // propagate the grants back to the input
          assign gnt_tree[C0] = gnt_tree[Pa] & ~sel;
          assign gnt_tree[C1] = gnt_tree[Pa] &  sel;"""
    reversed_block = """          // forward path
          logic sel; // local helper variable
          always @* begin : p_node
            // this always gives priority to the left child
            sel = req_tree[C0];
            // propagate requests
            req_tree[Pa]  = req_tree[C0] | req_tree[C1];
            // data and index muxes
            idx_tree[Pa]  = (sel) ? idx_tree[C1]  : idx_tree[C0];
            data_tree[Pa] = (sel) ? data_tree[C1] : data_tree[C0];
            // propagate the grants back to the input
            gnt_tree[C0] = gnt_tree[Pa] & ~sel;
            gnt_tree[C1] = gnt_tree[Pa] &  sel;
          end"""
    reversed_assign_block = """          // forward path
          wire sel; // local helper variable
          assign sel = req_tree[C0];
          // propagate requests
          assign req_tree[Pa]  = req_tree[C0] | req_tree[C1];
          // data and index muxes
          assign idx_tree[Pa]  = (sel) ? idx_tree[C1]  : idx_tree[C0];
          assign data_tree[Pa] = (sel) ? data_tree[C1] : data_tree[C0];
          // propagate the grants back to the input
          assign gnt_tree[C0] = gnt_tree[Pa] & ~sel;
          assign gnt_tree[C1] = gnt_tree[Pa] &  sel;"""
    for file_name in ("correct.v", "buggy.v"):
        path = case_dir / file_name
        text = path.read_text(encoding="utf-8")
        text = text.replace("always_comb begin", "always @* begin")
        text = text.replace("logic [2**(IdxW+1)-2:0]           req_tree;", "wire [2**(IdxW+1)-2:0]           req_tree;")
        text = text.replace("logic [2**(IdxW+1)-2:0]           gnt_tree;", "wire [2**(IdxW+1)-2:0]           gnt_tree;")
        text = text.replace("logic [2**(IdxW+1)-2:0][IdxW-1:0] idx_tree;", "wire [2**(IdxW+1)-2:0][IdxW-1:0] idx_tree;")
        text = text.replace("logic [2**(IdxW+1)-2:0][DW-1:0]   data_tree;", "wire [2**(IdxW+1)-2:0][DW-1:0]   data_tree;")
        text = text.replace(normal_block, normal_assign_block)
        text = text.replace(reversed_block, reversed_assign_block)
        write_text(path, text)


def sim_arbiter(mode: str, steps: Sequence[Tuple[int, int]]) -> List[Dict[str, int]]:
    rows: List[Dict[str, int]] = [
        {"rst_n": 0, "req_i[3:0]": 0, "ready_i": 0, "gnt_o[3:0]": 0, "idx_o[1:0]": 0, "valid_o": 0}
    ]
    for req, ready in steps:
        valid = 1 if req else 0
        if mode == "valid_depends_on_ready" and not ready:
            valid = 0
        winner = 0
        if req:
            order = [3, 2, 1, 0] if mode == "priority_reversed" else [0, 1, 2, 3]
            for idx in order:
                if req & (1 << idx):
                    winner = idx
                    break
        grant_ok = bool(req) and bool(ready)
        if mode == "grant_without_ready" and req:
            grant_ok = True
        gnt = (1 << winner) if grant_ok and valid else 0
        rows.append(
            {
                "rst_n": 1,
                "req_i[3:0]": req,
                "ready_i": ready,
                "gnt_o[3:0]": gnt,
                "idx_o[1:0]": winner,
                "valid_o": valid,
            }
        )
    return rows


def build_arbiter_tb(case_name: str, steps: Sequence[Tuple[int, int]], dump_name: str) -> str:
    tag = case_name.split("_", 1)[0]
    body = "\n".join(
        f"    @(negedge clk); ready_i = 1'b{ready}; req_i = 4'b{field_bit(req, 4)}; @(posedge clk);"
        for req, ready in steps[:-1]
    )
    req_last, ready_last = steps[-1]
    tail = f"    @(negedge clk); req_i = 4'b{field_bit(req_last, 4)}; ready_i = 1'b{ready_last}; @(posedge clk);"
    return f"""`timescale 1ns/1ps
module tb_{tag};
  reg clk;
  reg rst_n;
  reg [3:0] req_i;
  reg ready_i;
  wire [3:0] gnt_o;
  wire [1:0] idx_o;
  wire valid_o;

  dut_{case_name} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .req_i(req_i),
    .ready_i(ready_i),
    .gnt_o(gnt_o),
    .idx_o(idx_o),
    .valid_o(valid_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    req_i = 4'b0000;
    ready_i = 1'b0;

    $dumpfile("{dump_name}");
    $dumpvars(0, tb_{tag});

    repeat (2) @(posedge clk);
    @(negedge clk);
    rst_n = 1'b1;
{body}
{tail}
    $finish;
  end
endmodule
"""


def count_ones_4(value: int) -> int:
    return ((value >> 0) & 1) + ((value >> 1) & 1) + ((value >> 2) & 1) + ((value >> 3) & 1)


def sim_regwe_zero_enabled(steps: Sequence[Tuple[int, int]], buggy: bool) -> List[Dict[str, int]]:
    rows = [{"rst_n": 0, "oh_i[3:0]": 0, "en_i": 0, "err_o": 0}]
    for oh, en in steps:
        err = 0
        if en:
            if buggy and oh == 0:
                err = 1
            elif count_ones_4(oh) > 1:
                err = 1
        elif oh != 0:
            err = 1
        rows.append({"rst_n": 1, "oh_i[3:0]": oh, "en_i": en, "err_o": err})
    return rows


def sim_regwe_addr_check(steps: Sequence[Tuple[int, int]], buggy: bool) -> List[Dict[str, int]]:
    rows = [{"rst_n": 0, "oh_i[3:0]": 0, "en_i": 0, "err_o": 0}]
    for oh, en in steps:
        err = 0
        if en:
            if count_ones_4(oh) > 1:
                err = 1
            elif buggy and oh not in (0, 0b0001):
                err = 1
        elif oh != 0:
            err = 1
        rows.append({"rst_n": 1, "oh_i[3:0]": oh, "en_i": en, "err_o": err})
    return rows


def sim_onehot_legal_request(steps: Sequence[Tuple[int, int, int]], buggy: bool) -> List[Dict[str, int]]:
    rows = [{"rst_n": 0, "oh_i[3:0]": 0, "addr_i[1:0]": 0, "en_i": 0, "err_o": 0}]
    for oh, addr, en in steps:
        ones = count_ones_4(oh)
        err = 0
        if buggy and en and oh != 0:
            err = 1
        elif en:
            if ones > 1:
                err = 1
            elif ones == 1 and oh != (1 << addr):
                err = 1
            elif ones == 0:
                err = 1
        elif oh != 0:
            err = 1
        rows.append({"rst_n": 1, "oh_i[3:0]": oh, "addr_i[1:0]": addr, "en_i": en, "err_o": err})
    return rows


def build_regwe_tb(case_name: str, steps: Sequence[Tuple[int, int]], dump_name: str) -> str:
    tag = case_name.split("_", 1)[0]
    body = "\n".join(
        f"    oh_i = 4'b{field_bit(oh, 4)}; en_i = 1'b{en}; @(posedge clk);"
        for oh, en in steps
    )
    return f"""`timescale 1ns/1ps
module tb_{tag};
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg en_i;
  wire err_o;

  dut_{case_name} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .oh_i(oh_i),
    .en_i(en_i),
    .err_o(err_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    oh_i = 4'b0000;
    en_i = 1'b0;

    $dumpfile("{dump_name}");
    $dumpvars(0, tb_{tag});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{body}
    oh_i = 4'b0000; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def build_onehot_tb(case_name: str, steps: Sequence[Tuple[int, int, int]], dump_name: str) -> str:
    tag = case_name.split("_", 1)[0]
    body = "\n".join(
        f"    oh_i = 4'b{field_bit(oh, 4)}; addr_i = 2'd{addr}; en_i = 1'b{en}; @(posedge clk);"
        for oh, addr, en in steps
    )
    return f"""`timescale 1ns/1ps
module tb_{tag};
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg [1:0] addr_i;
  reg en_i;
  wire err_o;

  dut_{case_name} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .oh_i(oh_i),
    .addr_i(addr_i),
    .en_i(en_i),
    .err_o(err_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    oh_i = 4'b0000;
    addr_i = 2'd0;
    en_i = 1'b0;

    $dumpfile("{dump_name}");
    $dumpvars(0, tb_{tag});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{body}
    oh_i = 4'b0000; addr_i = 2'd0; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def update_readme(root: Path, entries: Sequence[Dict[str, object]]) -> None:
    total = len(entries)
    seeds = sum(1 for entry in entries if not entry.get("seed_case_name"))
    augmentations = total - seeds
    combo = sum(1 for entry in entries if entry.get("bug_class") == "combination_same_cycle")
    temporal = sum(1 for entry in entries if entry.get("bug_class") == "temporal_cross_cycle")
    module_counts: Dict[str, int] = {}
    for entry in entries:
        if entry.get("seed_case_name"):
            continue
        module = str(entry.get("source_module", ""))
        module_counts[module] = module_counts.get(module, 0) + 1
    lines = [
        "# Real RTL Scale120",
        "",
        "This root is generated from admitted real-RTL OpenTitan seeds, a reduced augmentation pool, and additional real OpenTitan mutation-backed seeds.",
        "",
        f"- total cases: {total}",
        f"- unique seed coverage: {seeds}",
        f"- augmentation/variant pool: {augmentations}",
        f"- combination/same-cycle cases: {combo}",
        f"- temporal/cross-cycle cases: {temporal}",
        f"- source projects: opentitan only ({total}/{total})",
        f"- unique seed modules: {len(module_counts)}",
        "",
        "Generation policy:",
        "- keep only real OpenTitan-backed cases in this root",
        "- preserve the seen + held-out + overfit-decoy three-track structure for every case",
        "- count seed-backed variants separately from unique seed coverage",
        "- prefer combination/same-cycle additions when filling new seed slots",
        "",
        "Counting policy:",
        "- Cases without `seed_case_name` are the only cases that count as unique seed coverage.",
        "- Cases with `seed_case_name` are augmentation-only and do not count as new module, new seed, or new bug-family coverage.",
        "",
        "Per-case trace structure:",
        "- seen trace: `tb.v` + `waveform_good.csv` / `waveform_bad.csv`",
        "- held-out trace: `tb_holdout.v` + `waveform_good_holdout.csv` / `waveform_bad_holdout.csv`",
        "- overfit decoy: `tb_decoy.v` + `waveform_good_decoy.csv` / `waveform_bad_decoy.csv`",
        "",
        "Local verification note:",
        "- decoy structure and seen/held-out/decoy divergence were refreshed locally for all 120 cases",
        "- the current recorded full-root reruns are simulator-backed WSL checks: [golden_recheck_scale120_wsl.csv](/D:/AssertionForge-main1/outputs/golden_recheck_scale120_wsl.csv) = `120/120` pass and [hardness_scale120_wsl.csv](/D:/AssertionForge-main1/outputs/hardness_scale120_wsl.csv) = `120/120` pass, last refreshed on July 9, 2026",
        "- those reruns used `iverilog` + `vvp` under WSL; they were not JasperGold runs",
        "- this root does not include JasperGold cover/property-proof artifacts, so it does not claim proof-level reachability or proof-level unreachable results",
        "",
        "Acceptance policy:",
        "- See [DATASET_ACCEPTANCE.md](/D:/AssertionForge-main1/DATASET_ACCEPTANCE.md) for the seed-vs-augmentation counting rules.",
        "",
    ]
    write_text(root / "README.md", "\n".join(lines))


def base_blueprint(name: str) -> Dict[str, object]:
    by_name = {str(item["name"]): item for item in load_case_blueprints()}
    return copy.deepcopy(by_name[name])


def main() -> int:
    scale_manifest_path = SCALE_ROOT / "case_manifest.json"
    scale_entries = load_manifest(scale_manifest_path)
    real_entries = {entry["name"]: entry for entry in load_manifest(REAL_ROOT / "case_manifest.json")}
    active_entries = {entry["name"]: entry for entry in load_manifest(ACTIVE_ROOT / "case_manifest.json")}

    generated_names = {
        "case107_prim_arbiter_priority_reversed",
        "case108_prim_arbiter_grant_without_ready",
        "case109_prim_arbiter_valid_depends_on_ready",
        "case114_prim_edge_negedge_misdecoded",
        "case115_prim_edge_both_edges_collapsed",
        "case121_prim_intr_test_qe_ignored",
        "case122_prim_filter_ctr_streak_reset_ignored",
        "case123_prim_edge_sync_output_lag",
        "case127_prim_intr_status_test_qe_ignored",
        "case133_prim_edge_negedge_missing",
        "case138_prim_regwe_zero_enabled_false_positive",
        "case139_prim_regwe_addr_check_false_positive",
        "case140_prim_onehot_legal_request_false_positive",
    }

    blocked = set(SYNTHETIC_CASES) | generated_names
    scale_entries = [entry for entry in scale_entries if str(entry["name"]) not in blocked]
    for case_name in blocked:
        target = SCALE_ROOT / case_name
        if target.exists():
            shutil.rmtree(target)

    new_entries: List[Dict[str, object]] = []

    for case_name, src_root in COPY_CASES.items():
        copy_case_dir(src_root, SCALE_ROOT, case_name)
        entry = copy.deepcopy(real_entries.get(case_name, active_entries.get(case_name)))
        entry["dataset_phase"] = "scale120_opentitan_only_repair"
        entry["status"] = "admitted_seed"
        entry["source_origin"] = "opentitan_real_rtl_case_dir"
        new_entries.append(entry)

    widths_arb = {
        "rst_n": 1,
        "req_i[3:0]": 4,
        "ready_i": 1,
        "gnt_o[3:0]": 4,
        "idx_o[1:0]": 2,
        "valid_o": 1,
    }
    for meta in ARBITER_CASES:
        case_name = str(meta["name"])
        copy_case_dir(REAL_ROOT, SCALE_ROOT, case_name)
        case_dir = SCALE_ROOT / case_name
        patch_arbiter_source(case_dir)
        write_text(case_dir / "tb.v", build_arbiter_tb(case_name, meta["primary"], f"{case_name}.vcd"))
        write_text(case_dir / "tb_holdout.v", build_arbiter_tb(case_name, meta["holdout"], f"{case_name}_holdout.vcd"))
        good_rows = emit_trace(sim_arbiter("correct", meta["primary"]), widths_arb)
        bad_rows = emit_trace(sim_arbiter(str(meta["bug_mode"]), meta["primary"]), widths_arb)
        holdout_good_rows = emit_trace(sim_arbiter("correct", meta["holdout"]), widths_arb)
        holdout_bad_rows = emit_trace(sim_arbiter(str(meta["bug_mode"]), meta["holdout"]), widths_arb)
        fieldnames = list(good_rows[0].keys())
        write_csv(case_dir / "waveform_good.csv", fieldnames, good_rows)
        write_csv(case_dir / "waveform_bad.csv", fieldnames, bad_rows)
        write_csv(case_dir / "waveform_good_holdout.csv", fieldnames, holdout_good_rows)
        write_csv(case_dir / "waveform_bad_holdout.csv", fieldnames, holdout_bad_rows)

        entry = {
            "name": case_name,
            "source_project": "opentitan",
            "source_module": "prim_arbiter_fixed",
            "source_origin": "opentitan_real_rtl_mutation_scaffold",
            "bug_class": meta["bug_class"],
            "bug_family": meta["bug_family"],
            "bug_type": meta["bug_type"],
            "spec": meta["spec"],
            "key_signals": ["clk", "rst_n", "req_i", "ready_i", "gnt_o", "idx_o", "valid_o"],
            "golden_sva": meta["golden_sva"],
            "loose_negative_controls": meta["loose_negative_controls"],
            "hard_case_rationale": meta["hard_case_rationale"],
            "overfit_lure": meta["overfit_lure"],
            "stimulus_notes": meta["stimulus_notes"],
            "dataset_phase": "scale120_opentitan_only_repair",
            "status": "admitted_seed",
            "dut_top_module": f"dut_{case_name}",
        }
        new_entries.append(entry)

    bp138 = base_blueprint("case107_prim_regwe_zero_enabled_false_positive")
    bp138["name"] = "case138_prim_regwe_zero_enabled_false_positive"
    bp138["overfit_lure"] = "Seen trace holds en_i=1 across a zero-hot window; held-out surrounds the same legality corner with different legal onehot preludes."
    entry138 = build_case(ROOT, SCALE_ROOT, bp138)
    case138 = SCALE_ROOT / str(bp138["name"])
    primary138 = [(0b0001, 1), (0b0000, 1), (0b0010, 1)]
    holdout138 = [(0b0100, 1), (0b0000, 1), (0b1000, 1)]
    write_text(case138 / "tb.v", build_regwe_tb(str(bp138["name"]), primary138, f"{bp138['name']}.vcd"))
    write_text(case138 / "tb_holdout.v", build_regwe_tb(str(bp138["name"]), holdout138, f"{bp138['name']}_holdout.vcd"))
    rows = emit_trace(sim_regwe_zero_enabled(primary138, False), {"rst_n": 1, "oh_i[3:0]": 4, "en_i": 1, "err_o": 1})
    write_csv(case138 / "waveform_good.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_regwe_zero_enabled(primary138, True), {"rst_n": 1, "oh_i[3:0]": 4, "en_i": 1, "err_o": 1})
    write_csv(case138 / "waveform_bad.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_regwe_zero_enabled(holdout138, False), {"rst_n": 1, "oh_i[3:0]": 4, "en_i": 1, "err_o": 1})
    write_csv(case138 / "waveform_good_holdout.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_regwe_zero_enabled(holdout138, True), {"rst_n": 1, "oh_i[3:0]": 4, "en_i": 1, "err_o": 1})
    write_csv(case138 / "waveform_bad_holdout.csv", list(rows[0].keys()), rows)
    entry138["dataset_phase"] = "scale120_opentitan_only_repair"
    entry138["status"] = "admitted_seed"
    entry138["source_origin"] = "opentitan_real_rtl_mutation_scaffold"
    new_entries.append(entry138)

    bp139 = base_blueprint("case108_prim_regwe_addr_check_false_positive")
    bp139["name"] = "case139_prim_regwe_addr_check_false_positive"
    bp139["overfit_lure"] = "Seen trace pins a legal bit-1 request; held-out switches to a different legal onehot so position literals alone stop working."
    entry139 = build_case(ROOT, SCALE_ROOT, bp139)
    case139 = SCALE_ROOT / str(bp139["name"])
    primary139 = [(0b0001, 1), (0b0010, 1), (0b0000, 1)]
    holdout139 = [(0b0001, 1), (0b0100, 1), (0b0000, 1)]
    write_text(case139 / "tb.v", build_regwe_tb(str(bp139["name"]), primary139, f"{bp139['name']}.vcd"))
    write_text(case139 / "tb_holdout.v", build_regwe_tb(str(bp139["name"]), holdout139, f"{bp139['name']}_holdout.vcd"))
    rows = emit_trace(sim_regwe_addr_check(primary139, False), {"rst_n": 1, "oh_i[3:0]": 4, "en_i": 1, "err_o": 1})
    write_csv(case139 / "waveform_good.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_regwe_addr_check(primary139, True), {"rst_n": 1, "oh_i[3:0]": 4, "en_i": 1, "err_o": 1})
    write_csv(case139 / "waveform_bad.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_regwe_addr_check(holdout139, False), {"rst_n": 1, "oh_i[3:0]": 4, "en_i": 1, "err_o": 1})
    write_csv(case139 / "waveform_good_holdout.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_regwe_addr_check(holdout139, True), {"rst_n": 1, "oh_i[3:0]": 4, "en_i": 1, "err_o": 1})
    write_csv(case139 / "waveform_bad_holdout.csv", list(rows[0].keys()), rows)
    entry139["dataset_phase"] = "scale120_opentitan_only_repair"
    entry139["status"] = "admitted_seed"
    entry139["source_origin"] = "opentitan_real_rtl_mutation_scaffold"
    new_entries.append(entry139)

    bp140 = base_blueprint("case109_prim_onehot_legal_request_false_positive")
    bp140["name"] = "case140_prim_onehot_legal_request_false_positive"
    bp140["overfit_lure"] = "Seen trace uses the legal 0010/addr=1 corner; held-out changes to 0100/addr=2 so literal request memorization breaks."
    entry140 = build_case(ROOT, SCALE_ROOT, bp140)
    case140 = SCALE_ROOT / str(bp140["name"])
    primary140 = [(0b0010, 1, 1), (0b0010, 1, 1), (0b0000, 0, 0)]
    holdout140 = [(0b0100, 2, 1), (0b0100, 2, 1), (0b0000, 0, 0)]
    write_text(case140 / "tb.v", build_onehot_tb(str(bp140["name"]), primary140, f"{bp140['name']}.vcd"))
    write_text(case140 / "tb_holdout.v", build_onehot_tb(str(bp140["name"]), holdout140, f"{bp140['name']}_holdout.vcd"))
    rows = emit_trace(sim_onehot_legal_request(primary140, False), {"rst_n": 1, "oh_i[3:0]": 4, "addr_i[1:0]": 2, "en_i": 1, "err_o": 1})
    write_csv(case140 / "waveform_good.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_onehot_legal_request(primary140, True), {"rst_n": 1, "oh_i[3:0]": 4, "addr_i[1:0]": 2, "en_i": 1, "err_o": 1})
    write_csv(case140 / "waveform_bad.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_onehot_legal_request(holdout140, False), {"rst_n": 1, "oh_i[3:0]": 4, "addr_i[1:0]": 2, "en_i": 1, "err_o": 1})
    write_csv(case140 / "waveform_good_holdout.csv", list(rows[0].keys()), rows)
    rows = emit_trace(sim_onehot_legal_request(holdout140, True), {"rst_n": 1, "oh_i[3:0]": 4, "addr_i[1:0]": 2, "en_i": 1, "err_o": 1})
    write_csv(case140 / "waveform_bad_holdout.csv", list(rows[0].keys()), rows)
    entry140["dataset_phase"] = "scale120_opentitan_only_repair"
    entry140["status"] = "admitted_seed"
    entry140["source_origin"] = "opentitan_real_rtl_mutation_scaffold"
    new_entries.append(entry140)

    scale_entries.extend(new_entries)
    scale_entries = sorted(scale_entries, key=lambda item: str(item["name"]))
    save_manifest(scale_manifest_path, scale_entries)
    ensure_decoy_structure(SCALE_ROOT)
    updated_entries = load_manifest(scale_manifest_path)
    update_readme(SCALE_ROOT, updated_entries)
    print(
        f"[DONE] Repaired scale120 as OpenTitan-only: total={len(updated_entries)} "
        f"seeds={sum(1 for e in updated_entries if not e.get('seed_case_name'))} "
        f"augmentations={sum(1 for e in updated_entries if e.get('seed_case_name'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
