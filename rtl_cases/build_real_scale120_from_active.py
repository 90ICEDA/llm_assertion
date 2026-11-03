#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

from decoy_structure import ensure_decoy_structure


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ROOT = ROOT / "rtl_cases_real_active"
DEFAULT_OUTPUT = ROOT / "rtl_cases_real_scale120"

EXCLUDED_ORIGINALS = {
    "case114_prim_edge_negedge_misdecoded",
    "case115_prim_edge_both_edges_collapsed",
    "case133_prim_edge_negedge_missing",
}


def load_manifest(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def copy_seed_case(seed_dir: Path, out_dir: Path, *, copy_waveforms: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for child in seed_dir.iterdir():
        if child.name == "experiment":
            continue
        if child.name.startswith("waveform_") and not copy_waveforms:
            continue
        if child.is_dir():
            shutil.copytree(child, out_dir / child.name, dirs_exist_ok=True)
        else:
            shutil.copy2(child, out_dir / child.name)


def render_onehot_tb(
    *,
    case_name: str,
    top: str,
    primary_rows: Sequence[Tuple[str, str, str]],
    holdout_rows: Sequence[Tuple[str, str, str]],
) -> Tuple[str, str]:
    def block(rows: Sequence[Tuple[str, str, str]]) -> str:
        return "\n".join(
            f"    en_i = 1'b1; oh_i = 4'b{oh}; addr_i = 2'd{addr}; @(posedge clk);"
            if en == "1"
            else f"    en_i = 1'b0; oh_i = 4'b{oh}; addr_i = 2'd{addr}; @(posedge clk);"
            for oh, addr, en in rows
        )

    def render(vcd_name: str, stimulus_block: str) -> str:
        return f"""`timescale 1ns/1ps
module tb_{case_name.split("_", 1)[0]};
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg [1:0] addr_i;
  reg en_i;
  wire err_o;

  {top} u_dut (
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

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_name.split("_", 1)[0]});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus_block}
    oh_i = 4'b0000; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""

    return (
        render(f"{case_name.split('_', 1)[0]}.vcd", block(primary_rows)),
        render(f"{case_name.split('_', 1)[0]}_holdout.vcd", block(holdout_rows)),
    )


def render_regwe_tb(
    *,
    case_name: str,
    top: str,
    primary_rows: Sequence[Tuple[str, str]],
    holdout_rows: Sequence[Tuple[str, str]],
) -> Tuple[str, str]:
    def block(rows: Sequence[Tuple[str, str]]) -> str:
        return "\n".join(
            f"    en_i = 1'b{en}; oh_i = 4'b{oh}; @(posedge clk);"
            for oh, en in rows
        )

    def render(vcd_name: str, stimulus_block: str) -> str:
        return f"""`timescale 1ns/1ps
module tb_{case_name.split("_", 1)[0]};
  reg clk;
  reg rst_n;
  reg [3:0] oh_i;
  reg en_i;
  wire err_o;

  {top} u_dut (
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

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_name.split("_", 1)[0]});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus_block}
    oh_i = 4'b0000; en_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""

    return (
        render(f"{case_name.split('_', 1)[0]}.vcd", block(primary_rows)),
        render(f"{case_name.split('_', 1)[0]}_holdout.vcd", block(holdout_rows)),
    )


def render_fifo_tb(
    *,
    case_name: str,
    top: str,
    primary_ops: Sequence[Tuple[int, int, int]],
    holdout_ops: Sequence[Tuple[int, int, int]],
) -> Tuple[str, str]:
    def block(ops: Sequence[Tuple[int, int, int]]) -> str:
        return "\n".join(
            f"    clr_i = 1'b{clr}; incr_wptr_i = 1'b{w}; incr_rptr_i = 1'b{r}; @(posedge clk);"
            for clr, w, r in ops
        )

    def render(vcd_name: str, stimulus_block: str) -> str:
        return f"""`timescale 1ns/1ps
module tb_{case_name.split("_", 1)[0]};
  reg clk;
  reg rst_n;
  reg clr_i;
  reg incr_wptr_i;
  reg incr_rptr_i;
  wire [1:0] wptr_o;
  wire [1:0] rptr_o;
  wire full_o;
  wire empty_o;
  wire [2:0] depth_o;
  wire err_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
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

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    clr_i = 1'b0;
    incr_wptr_i = 1'b0;
    incr_rptr_i = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_name.split("_", 1)[0]});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus_block}
    clr_i = 1'b0; incr_wptr_i = 1'b0; incr_rptr_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""

    return (
        render(f"{case_name.split('_', 1)[0]}.vcd", block(primary_ops)),
        render(f"{case_name.split('_', 1)[0]}_holdout.vcd", block(holdout_ops)),
    )


def render_intr_mask_tb(
    *,
    case_name: str,
    top: str,
    primary_steps: Sequence[str],
    holdout_steps: Sequence[str],
) -> Tuple[str, str]:
    def render(vcd_name: str, stimulus_lines: Sequence[str]) -> str:
        stimulus_block = "\n".join(f"    {line}" for line in stimulus_lines)
        return f"""`timescale 1ns/1ps
module tb_{case_name.split("_", 1)[0]};
  reg clk;
  reg rst_n;
  reg event_intr_i;
  reg reg2hw_intr_enable_q_i;
  reg reg2hw_intr_test_q_i;
  reg reg2hw_intr_test_qe_i;
  reg reg2hw_intr_state_q_i;
  reg sw_clear;
  wire hw2reg_intr_state_de_o;
  wire hw2reg_intr_state_d_o;
  wire intr_o;

  {top} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .event_intr_i(event_intr_i),
    .reg2hw_intr_enable_q_i(reg2hw_intr_enable_q_i),
    .reg2hw_intr_test_q_i(reg2hw_intr_test_q_i),
    .reg2hw_intr_test_qe_i(reg2hw_intr_test_qe_i),
    .reg2hw_intr_state_q_i(reg2hw_intr_state_q_i),
    .hw2reg_intr_state_de_o(hw2reg_intr_state_de_o),
    .hw2reg_intr_state_d_o(hw2reg_intr_state_d_o),
    .intr_o(intr_o)
  );

  always #5 clk = ~clk;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reg2hw_intr_state_q_i <= 1'b0;
    end else if (sw_clear) begin
      reg2hw_intr_state_q_i <= 1'b0;
    end else if (hw2reg_intr_state_de_o) begin
      reg2hw_intr_state_q_i <= hw2reg_intr_state_d_o;
    end
  end

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    event_intr_i = 1'b0;
    reg2hw_intr_enable_q_i = 1'b0;
    reg2hw_intr_test_q_i = 1'b0;
    reg2hw_intr_test_qe_i = 1'b0;
    sw_clear = 1'b0;

    $dumpfile("{vcd_name}");
    $dumpvars(0, tb_{case_name.split("_", 1)[0]});

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus_block}
    event_intr_i = 1'b0; reg2hw_intr_enable_q_i = 1'b0; sw_clear = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""

    return (
        render(f"{case_name.split('_', 1)[0]}.vcd", primary_steps),
        render(f"{case_name.split('_', 1)[0]}_holdout.vcd", holdout_steps),
    )


def onehot_enable_rows(pre_legal: str, bad_zero: str, post_legal: str) -> List[Tuple[str, str, str]]:
    del bad_zero
    return [
        (pre_legal, str(int(pre_legal, 2).bit_length() - 1), "1"),
        ("0000", "0", "1"),
        ("0000", "0", "1"),
        (post_legal, str(int(post_legal, 2).bit_length() - 1), "1"),
    ]


def regwe_rows(bad_oh: str, legal_oh: str) -> List[Tuple[str, str]]:
    return [
        (bad_oh, "0"),
        (bad_oh, "0"),
        (legal_oh, "1"),
        ("0000", "1"),
    ]


def full_ops(variant: int) -> Tuple[List[Tuple[int, int, int]], List[Tuple[int, int, int]]]:
    patterns = [
        [(0, 1, 0)] * 3 + [(0, 0, 0), (0, 1, 0)],
        [(0, 1, 0), (0, 1, 0), (0, 0, 0), (0, 1, 0), (0, 0, 0)],
        [(0, 1, 0), (0, 0, 0), (0, 1, 0), (0, 1, 0), (0, 0, 0)],
    ]
    primary = patterns[variant % len(patterns)]
    holdout = [
        (0, 1, 0),
        (0, 1, 0),
        (0, 0, 1),
        (0, 1, 0),
        (0, 1, 0),
        (0, 0, 1),
        (0, 0, 1),
        (1, 0, 0),
        (0, 0, 0),
        (0, 1, 0),
        (0, 1, 0),
        (0, 1, 0),
        (0, 1, 0),
    ]
    return primary, holdout


def empty_ops(variant: int) -> Tuple[List[Tuple[int, int, int]], List[Tuple[int, int, int]]]:
    patterns = [
        ([(0, 1, 0), (0, 1, 0), (0, 0, 1), (0, 0, 1)], [(0, 1, 0), (0, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 1)]),
        ([(0, 1, 0), (0, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 1)], [(0, 1, 0), (0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 0, 1)]),
        ([(0, 1, 0), (0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 0, 1)], [(0, 1, 0), (0, 0, 1), (0, 1, 0), (0, 0, 1)]),
    ]
    return patterns[variant % len(patterns)]


def empty_early_ops(variant: int) -> Tuple[List[Tuple[int, int, int]], List[Tuple[int, int, int]]]:
    patterns = [
        ([(0, 1, 0), (0, 1, 0), (0, 0, 1)], [(0, 1, 0), (0, 0, 0), (0, 1, 0), (0, 0, 1)]),
        ([(0, 1, 0), (0, 0, 0), (0, 1, 0), (0, 0, 1)], [(0, 1, 0), (0, 1, 0), (0, 0, 0), (0, 0, 1)]),
        ([(0, 1, 0), (0, 1, 0), (0, 0, 0), (0, 0, 1)], [(0, 1, 0), (0, 0, 1), (0, 1, 0)]),
    ]
    return patterns[variant % len(patterns)]


def depth_ops(variant: int) -> Tuple[List[Tuple[int, int, int]], List[Tuple[int, int, int]]]:
    patterns = [
        [(0, 1, 0), (0, 0, 0), (0, 0, 0), (0, 0, 1), (0, 0, 1)],
        [(0, 1, 0), (0, 1, 0), (0, 0, 1), (0, 0, 1)],
        [(0, 1, 0), (0, 0, 1), (0, 0, 0)],
    ]
    primary = patterns[variant % len(patterns)]
    holdout = [
        (0, 1, 0),
        (0, 1, 0),
        (0, 0, 1),
        (0, 1, 0),
        (0, 1, 0),
        (0, 0, 1),
        (0, 0, 1),
        (1, 0, 0),
        (0, 0, 0),
        (0, 1, 0),
        (0, 1, 0),
        (0, 1, 0),
        (0, 1, 0),
    ]
    return primary, holdout


def intr_steps(mask_drop_after: int, clear_before: bool) -> Tuple[List[str], List[str]]:
    primary = [
        "reg2hw_intr_enable_q_i = 1'b1;",
        "event_intr_i = 1'b1; @(posedge clk);",
        "event_intr_i = 1'b0; @(posedge clk);",
    ]
    primary.extend(["@(posedge clk);"] * mask_drop_after)
    primary.append("reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);")
    primary.append("reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);")
    if clear_before:
        primary.append("sw_clear = 1'b1; @(posedge clk);")
        primary.append("sw_clear = 1'b0; @(posedge clk);")

    holdout = [
        "reg2hw_intr_enable_q_i = 1'b1;",
        "event_intr_i = 1'b1; @(posedge clk);",
        "event_intr_i = 1'b0; @(posedge clk);",
        "@(posedge clk);",
        "reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);",
        "reg2hw_intr_enable_q_i = 1'b0; @(posedge clk);",
        "reg2hw_intr_enable_q_i = 1'b1; @(posedge clk);",
    ]
    return primary, holdout


def variant_entry(
    *,
    seed_entry: Dict[str, object],
    new_name: str,
    new_bug_type: str,
    golden_sva: str,
    overfit_lure: str,
    stimulus_notes: str,
) -> Dict[str, object]:
    entry = deepcopy(seed_entry)
    entry["name"] = new_name
    entry["bug_type"] = new_bug_type
    entry["overfit_lure"] = overfit_lure
    entry["stimulus_notes"] = stimulus_notes
    entry["seed_case_name"] = str(seed_entry["name"])
    entry["golden_sva"] = deepcopy(seed_entry["golden_sva"])
    entry["golden_sva"]["sva"] = golden_sva
    entry["dut_top_module"] = str(seed_entry.get("dut_top_module", ""))
    return entry


def build_scale120_dataset(active_root: Path, out_root: Path) -> None:
    entries = load_manifest(active_root)
    entry_by_name = {str(entry["name"]): entry for entry in entries}

    base_entries = [entry for entry in entries if str(entry["name"]) not in EXCLUDED_ORIGINALS]
    out_root.mkdir(parents=True, exist_ok=True)

    for entry in base_entries:
        seed_name = str(entry["name"])
        copy_seed_case(active_root / seed_name, out_root / seed_name, copy_waveforms=True)

    generated_entries: List[Dict[str, object]] = []
    next_case_num = 201

    def alloc_name(seed_name: str, tag: str) -> str:
        nonlocal next_case_num
        name = f"case{next_case_num}_{tag}_from_{seed_name}"
        next_case_num += 1
        return name

    onehot_multihot_contexts = [
        ("0001", "0010", "0010", "0001"),
        ("0010", "0001", "0001", "0010"),
        ("0100", "0001", "0010", "0100"),
        ("0001", "0100", "0100", "0001"),
        ("0010", "0100", "0001", "0100"),
        ("0100", "0010", "0100", "0010"),
        ("0001", "1000", "0010", "1000"),
        ("1000", "0001", "1000", "0010"),
    ]
    seed = entry_by_name["case101_prim_onehot_multihot_suppressed"]
    top = str(seed["dut_top_module"])
    for idx, (pre_seen, post_seen, pre_hold, post_hold) in enumerate(onehot_multihot_contexts, start=1):
        name = alloc_name(str(seed["name"]), f"onehot_multihot_v{idx}")
        seen_bad = "1010"
        holdout_bad = "1100"
        tb, tb_holdout = render_onehot_tb(
            case_name=name,
            top=top,
            primary_rows=[(pre_seen, str(int(pre_seen, 2).bit_length() - 1), "1"), (seen_bad, "1", "1"), (seen_bad, "1", "1"), (post_seen, str(int(post_seen, 2).bit_length() - 1), "1")],
            holdout_rows=[(pre_hold, str(int(pre_hold, 2).bit_length() - 1), "1"), (holdout_bad, "2", "1"), (holdout_bad, "2", "1"), (post_hold, str(int(post_hold, 2).bit_length() - 1), "1")],
        )
        golden = (
            "assert property (@(posedge clk) disable iff (!rst_n) "
            f"((((oh_i == 4'b{seen_bad}) && ($past(oh_i) == 4'b{seen_bad})) || "
            f"((oh_i == 4'b{holdout_bad}) && ($past(oh_i) == 4'b{holdout_bad}))) && "
            "en_i && $past(en_i)) |-> err_o);"
        )
        entry = variant_entry(
            seed_entry=seed,
            new_name=name,
            new_bug_type=f"multihot error suppressed variant {idx}",
            golden_sva=golden,
            overfit_lure=f"Seen trace still uses bug-revealing literal 4'b{seen_bad}, but the surrounding legal context changes; held-out keeps 4'b{holdout_bad}.",
            stimulus_notes="Primary and held-out preserve the same multihot trigger while changing the surrounding legal onehot context.",
        )
        copy_seed_case(active_root / str(seed["name"]), out_root / name, copy_waveforms=False)
        write_text(out_root / name / "tb.v", tb)
        write_text(out_root / name / "tb_holdout.v", tb_holdout)
        generated_entries.append(entry)

    zerohot_variants = [
        ("0001", "0100", "0010", "1000"),
        ("0010", "1000", "0001", "0100"),
        ("0100", "0001", "1000", "0010"),
        ("1000", "0010", "0100", "0001"),
        ("0001", "1000", "0010", "0100"),
        ("0010", "0100", "1000", "0001"),
        ("0100", "1000", "0001", "0010"),
        ("1000", "0001", "0100", "0010"),
    ]
    for seed_name in [
        "case102_prim_onehot_enable_mismatch_suppressed",
        "case129_prim_onehot_zero_enabled_suppressed",
    ]:
        seed = entry_by_name[seed_name]
        top = str(seed["dut_top_module"])
        for idx, (pre_seen, post_seen, pre_hold, post_hold) in enumerate(zerohot_variants, start=1):
            name = alloc_name(seed_name, f"onehot_zerohot_v{idx}")
            tb, tb_holdout = render_onehot_tb(
                case_name=name,
                top=top,
                primary_rows=[(pre_seen, str(int(pre_seen, 2).bit_length() - 1), "1"), ("0000", "0", "1"), ("0000", "0", "1"), (post_seen, str(int(post_seen, 2).bit_length() - 1), "1")],
                holdout_rows=[(pre_hold, str(int(pre_hold, 2).bit_length() - 1), "1"), ("0000", "0", "1"), ("0000", "0", "1"), (post_hold, str(int(post_hold, 2).bit_length() - 1), "1")],
            )
            entry = variant_entry(
                seed_entry=seed,
                new_name=name,
                new_bug_type=f"{seed['bug_type']} variant {idx}",
                golden_sva=str(seed["golden_sva"]["sva"]),
                overfit_lure=f"Seen legal wrappers use {pre_seen}/{post_seen}; held-out uses {pre_hold}/{post_hold} around the same zero-hot mismatch.",
                stimulus_notes="Both seen and held-out keep the zero-hot-while-enabled bug trigger, but surround it with different legal onehot positions.",
            )
            copy_seed_case(active_root / seed_name, out_root / name, copy_waveforms=False)
            write_text(out_root / name / "tb.v", tb)
            write_text(out_root / name / "tb_holdout.v", tb_holdout)
            generated_entries.append(entry)

    addr_pairs = [
        (("0100", "0"), ("0010", "0")),
        (("1000", "1"), ("0001", "1")),
        (("0010", "3"), ("0100", "1")),
        (("0001", "2"), ("1000", "0")),
        (("0100", "1"), ("0010", "3")),
        (("1000", "0"), ("0001", "2")),
        (("0010", "0"), ("1000", "1")),
        (("0001", "1"), ("0100", "0")),
    ]
    seed = entry_by_name["case103_prim_onehot_addr_mismatch_suppressed"]
    top = str(seed["dut_top_module"])
    for idx, ((seen_oh, seen_addr), (hold_oh, hold_addr)) in enumerate(addr_pairs, start=1):
        name = alloc_name(str(seed["name"]), f"onehot_addr_bad_v{idx}")
        seen_good_addr = str(int(seen_oh, 2).bit_length() - 1)
        hold_good_addr = str(int(hold_oh, 2).bit_length() - 1)
        tb, tb_holdout = render_onehot_tb(
            case_name=name,
            top=top,
            primary_rows=[(seen_oh, seen_good_addr, "1"), (seen_oh, seen_addr, "1"), (seen_oh, seen_addr, "1"), (seen_oh, seen_good_addr, "1")],
            holdout_rows=[(hold_oh, hold_good_addr, "1"), (hold_oh, hold_addr, "1"), (hold_oh, hold_addr, "1"), (hold_oh, hold_good_addr, "1")],
        )
        golden = (
            "assert property (@(posedge clk) disable iff (!rst_n) "
            f"((((oh_i == 4'b{seen_oh}) && ($past(oh_i) == 4'b{seen_oh}) && (addr_i == 2'd{seen_addr}) && ($past(addr_i) == 2'd{seen_addr})) || "
            f"((oh_i == 4'b{hold_oh}) && ($past(oh_i) == 4'b{hold_oh}) && (addr_i == 2'd{hold_addr}) && ($past(addr_i) == 2'd{hold_addr}))) && "
            "en_i && $past(en_i)) |-> err_o);"
        )
        entry = variant_entry(
            seed_entry=seed,
            new_name=name,
            new_bug_type=f"address mismatch error suppressed variant {idx}",
            golden_sva=golden,
            overfit_lure=f"Seen mismatch pair is (4'b{seen_oh}, {seen_addr}); held-out swaps to (4'b{hold_oh}, {hold_addr}).",
            stimulus_notes="Primary and held-out both use onehot/address mismatches, but on different active bits and wrong indices.",
        )
        copy_seed_case(active_root / str(seed["name"]), out_root / name, copy_waveforms=False)
        write_text(out_root / name / "tb.v", tb)
        write_text(out_root / name / "tb_holdout.v", tb_holdout)
        generated_entries.append(entry)

    seed = entry_by_name["case137_prim_onehot_addr_false_positive"]
    top = str(seed["dut_top_module"])
    legal_pairs = [
        (("0001", "0"), ("0010", "1")),
        (("0010", "1"), ("0100", "2")),
        (("0100", "2"), ("1000", "3")),
        (("1000", "3"), ("0001", "0")),
        (("0010", "1"), ("1000", "3")),
        (("0100", "2"), ("0001", "0")),
        (("1000", "3"), ("0010", "1")),
        (("0001", "0"), ("0100", "2")),
    ]
    for idx, ((seen_oh, seen_addr), (hold_oh, hold_addr)) in enumerate(legal_pairs, start=1):
        name = alloc_name(str(seed["name"]), f"onehot_addr_legal_v{idx}")
        tb, tb_holdout = render_onehot_tb(
            case_name=name,
            top=top,
            primary_rows=[(seen_oh, seen_addr, "1"), ("0100", "0", "1"), ("0100", "2", "0"), (seen_oh, seen_addr, "1"), (seen_oh, seen_addr, "1"), ("1010", "1", "1")],
            holdout_rows=[(hold_oh, hold_addr, "1"), ("0010", "0", "1"), ("1000", "3", "0"), (hold_oh, hold_addr, "1"), (hold_oh, hold_addr, "1"), ("1100", "2", "1")],
        )
        golden = (
            "assert property (@(posedge clk) disable iff (!rst_n) "
            f"((((oh_i == 4'b{seen_oh}) && ($past(oh_i) == 4'b{seen_oh}) && (addr_i == 2'd{seen_addr}) && ($past(addr_i) == 2'd{seen_addr})) || "
            f"((oh_i == 4'b{hold_oh}) && ($past(oh_i) == 4'b{hold_oh}) && (addr_i == 2'd{hold_addr}) && ($past(addr_i) == 2'd{hold_addr}))) && "
            "en_i && $past(en_i)) |-> !err_o);"
        )
        entry = variant_entry(
            seed_entry=seed,
            new_name=name,
            new_bug_type=f"legal onehot request false positive variant {idx}",
            golden_sva=golden,
            overfit_lure=f"Seen legal pair is (4'b{seen_oh}, {seen_addr}); held-out legal pair is (4'b{hold_oh}, {hold_addr}).",
            stimulus_notes="Both seen and held-out include legal onehot/address matches plus unrelated illegal distractors to preserve the false-positive check.",
        )
        copy_seed_case(active_root / str(seed["name"]), out_root / name, copy_waveforms=False)
        write_text(out_root / name / "tb.v", tb)
        write_text(out_root / name / "tb_holdout.v", tb_holdout)
        generated_entries.append(entry)

    seed = entry_by_name["case126_prim_regwe_enable_gap"]
    top = str(seed["dut_top_module"])
    regwe_variants = [
        ("0100", "0001"),
        ("0010", "1000"),
        ("1000", "0010"),
        ("0001", "0100"),
        ("0100", "0010"),
        ("0010", "0001"),
        ("1000", "0100"),
    ]
    for idx, (bad_oh, legal_oh) in enumerate(regwe_variants, start=1):
        name = alloc_name(str(seed["name"]), f"regwe_enable_gap_v{idx}")
        tb, tb_holdout = render_regwe_tb(
            case_name=name,
            top=top,
            primary_rows=regwe_rows(bad_oh, legal_oh),
            holdout_rows=regwe_rows(legal_oh, bad_oh if bad_oh != "0000" else "0010"),
        )
        entry = variant_entry(
            seed_entry=seed,
            new_name=name,
            new_bug_type=f"regwe enable gap variant {idx}",
            golden_sva=str(seed["golden_sva"]["sva"]),
            overfit_lure=f"Seen disabled-nonzero request uses 4'b{bad_oh}; held-out flips to a different active mask.",
            stimulus_notes="The same disabled-nonzero bug trigger appears in both traces, but the nonzero onehot mask changes between seen and held-out.",
        )
        copy_seed_case(active_root / str(seed["name"]), out_root / name, copy_waveforms=False)
        write_text(out_root / name / "tb.v", tb)
        write_text(out_root / name / "tb_holdout.v", tb_holdout)
        generated_entries.append(entry)

    fifo_families = [
        ("case104_prim_fifo_full_early", full_ops, 9),
        ("case105_prim_fifo_empty_late", empty_ops, 9),
        ("case106_prim_fifo_depth_off_by_one", depth_ops, 9),
        ("case130_prim_fifo_empty_early", empty_early_ops, 9),
    ]
    for seed_name, op_builder, variant_count in fifo_families:
        seed = entry_by_name[seed_name]
        top = str(seed["dut_top_module"])
        for idx in range(variant_count):
            name = alloc_name(seed_name, f"fifo_v{idx + 1}")
            primary_ops, holdout_ops = op_builder(idx)
            tb, tb_holdout = render_fifo_tb(
                case_name=name,
                top=top,
                primary_ops=primary_ops,
                holdout_ops=holdout_ops,
            )
            entry = variant_entry(
                seed_entry=seed,
                new_name=name,
                new_bug_type=f"{seed['bug_type']} variant {idx + 1}",
                golden_sva=str(seed["golden_sva"]["sva"]),
                overfit_lure="Seen and held-out reach the same FIFO boundary through different write/read preludes.",
                stimulus_notes="Both traces preserve the same sampled FIFO boundary semantics while changing the path taken to reach that occupancy/window.",
            )
            copy_seed_case(active_root / seed_name, out_root / name, copy_waveforms=False)
            write_text(out_root / name / "tb.v", tb)
            write_text(out_root / name / "tb_holdout.v", tb_holdout)
            generated_entries.append(entry)

    intr_variants = [
        (0, False),
        (1, False),
        (2, False),
        (0, False),
        (1, False),
    ]
    for seed_name in [
        "case111_prim_intr_output_or_mask",
        "case135_prim_intr_enable_mask_ignored",
    ]:
        seed = entry_by_name[seed_name]
        top = str(seed["dut_top_module"])
        for idx, (idle, do_clear) in enumerate(intr_variants, start=1):
            name = alloc_name(seed_name, f"intr_mask_v{idx}")
            primary_steps, holdout_steps = intr_steps(idle, do_clear)
            tb, tb_holdout = render_intr_mask_tb(
                case_name=name,
                top=top,
                primary_steps=primary_steps,
                holdout_steps=holdout_steps,
            )
            entry = variant_entry(
                seed_entry=seed,
                new_name=name,
                new_bug_type=f"{seed['bug_type']} variant {idx}",
                golden_sva=str(seed["golden_sva"]["sva"]),
                overfit_lure="Seen and held-out both mask an already-latched interrupt state, but differ in idle spacing and clear prelude.",
                stimulus_notes="The masked-state corner is preserved while the event-to-state prelude differs between primary and held-out traces.",
            )
            copy_seed_case(active_root / seed_name, out_root / name, copy_waveforms=False)
            write_text(out_root / name / "tb.v", tb)
            write_text(out_root / name / "tb_holdout.v", tb_holdout)
            generated_entries.append(entry)

    all_entries = base_entries + generated_entries
    manifest = {"cases": all_entries}
    write_text(out_root / "case_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    ensure_decoy_structure(out_root)
    all_entries = load_manifest(out_root)
    combo = sum(1 for entry in all_entries if entry.get("bug_class") == "combination_same_cycle")
    temporal = sum(1 for entry in all_entries if entry.get("bug_class") == "temporal_cross_cycle")
    seeds = [entry for entry in all_entries if not entry.get("seed_case_name")]
    augments = [entry for entry in all_entries if entry.get("seed_case_name")]
    projects = sorted({str(entry.get("source_project", "")).strip() for entry in all_entries if str(entry.get("source_project", "")).strip()})
    readme = "\n".join(
        [
            "# Real RTL Scale120",
            "",
            "This root is generated from the admitted active real-RTL seeds plus same-bug stimulus/literal variants.",
            "",
            f"- total cases: {len(all_entries)}",
            f"- unique seed coverage: {len(seeds)}",
            f"- augmentation/variant pool: {len(augments)}",
            f"- combination/same-cycle cases: {combo}",
            f"- temporal/cross-cycle cases: {temporal}",
            f"- source projects: {', '.join(projects) if projects else '(none)'}",
            "",
            "Generation policy:",
            "- keep only seed cases that already passed the strict golden self-check gate",
            "- expand mainly same-cycle families with seen/held-out literal and prelude variants",
            "- enforce a three-track structure per case: seen trace, held-out trace, and explicit overfit decoy",
            "- preserve the existing good/bad/heldout structure while adding `tb_decoy.v` plus `waveform_*_decoy.csv` artifacts",
            "",
        ]
    )
    write_text(out_root / "README.md", readme)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a ~120-case OpenTitan-heavy scaleout root from active admitted seeds.")
    parser.add_argument("--active-root", default=str(ACTIVE_ROOT), help="Input root containing active admitted cases.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT), help="Output dataset root.")
    args = parser.parse_args()

    active_root = Path(args.active_root).resolve()
    out_root = Path(args.output_root).resolve()
    build_scale120_dataset(active_root, out_root)
    print(f"[DONE] Built scaleout dataset at {out_root}")


if __name__ == "__main__":
    main()
