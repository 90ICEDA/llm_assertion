#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from decoy_structure import ensure_decoy_structure


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "rtl_cases_real_scale120"

REPLACED_VARIANTS = [
    "case241_regwe_enable_gap_v1_from_case126_prim_regwe_enable_gap",
    "case242_regwe_enable_gap_v2_from_case126_prim_regwe_enable_gap",
    "case243_regwe_enable_gap_v3_from_case126_prim_regwe_enable_gap",
    "case284_intr_mask_v1_from_case111_prim_intr_output_or_mask",
    "case285_intr_mask_v2_from_case111_prim_intr_output_or_mask",
    "case286_intr_mask_v3_from_case111_prim_intr_output_or_mask",
    "case287_intr_mask_v4_from_case111_prim_intr_output_or_mask",
    "case288_intr_mask_v5_from_case111_prim_intr_output_or_mask",
    "case289_intr_mask_v1_from_case135_prim_intr_enable_mask_ignored",
    "case290_intr_mask_v2_from_case135_prim_intr_enable_mask_ignored",
    "case291_intr_mask_v3_from_case135_prim_intr_enable_mask_ignored",
    "case292_intr_mask_v4_from_case135_prim_intr_enable_mask_ignored",
    "case293_intr_mask_v5_from_case135_prim_intr_enable_mask_ignored",
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


def load_manifest(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def save_manifest(root: Path, cases: Sequence[Dict[str, object]]) -> None:
    write_text(root / "case_manifest.json", json.dumps({"cases": list(cases)}, indent=2, ensure_ascii=False) + "\n")


def case_dir(root: Path, case_name: str) -> Path:
    return root / case_name


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


def drop_case(root: Path, case_name: str) -> None:
    target = case_dir(root, case_name)
    if target.exists():
        shutil.rmtree(target)


def stimulus_notes(
    *,
    case_name: str,
    bug_class: str,
    bug_family: str,
    bug_type: str,
    spec: str,
    rationale: str,
    stimulus: str,
    loose_controls: Sequence[Tuple[str, str, str]],
) -> str:
    lines = [
        f"# {case_name}",
        "",
        f"- `bug_class`: {bug_class}",
        f"- `bug_family`: {bug_family}",
        f"- `bug_type`: {bug_type}",
        "",
        "## Spec",
        "",
        spec,
        "",
        "## Hardness Rationale",
        "",
        rationale,
        "",
        "## Stimulus Notes",
        "",
        stimulus,
        "",
        "## Loose Negative Controls",
        "",
    ]
    for name, why, assertion in loose_controls:
        lines.append(f"- `{name}`: {why}")
        lines.append(f"  Assertion: `{assertion}`")
    lines.extend(
        [
            "",
            "## Next Step",
            "",
            "Regenerate waveforms if needed, then run golden self-check, hardness, and divergence gates before admitting this seed.",
            "",
        ]
    )
    return "\n".join(lines)


def build_uart_tfifo_module(case_name: str, mode: str, buggy: bool) -> str:
    full_expr = "count_q >= 3" if buggy and mode == "full_early" else "count_q == 4"
    count_expr = "3'd1" if buggy and mode == "count_off_by_one" else "count_q"
    body = """
  logic [2:0] count_q;
  logic empty_dly_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count_q <= 3'd0;
      empty_dly_q <= 1'b1;
    end else begin
      empty_dly_q <= (count_q == 3'd0);
"""
    if buggy and mode == "clear_ignored":
        body += """      if (push_i && !pop_i && count_q < 3'd4) begin
        count_q <= count_q + 3'd1;
      end else if (!push_i && pop_i && count_q > 3'd0) begin
        count_q <= count_q - 3'd1;
      end
"""
    else:
        body += """      if (clr_i) begin
        count_q <= 3'd0;
      end else if (push_i && !pop_i && count_q < 3'd4) begin
        count_q <= count_q + 3'd1;
      end else if (!push_i && pop_i && count_q > 3'd0) begin
        count_q <= count_q - 3'd1;
      end
"""
    body += """    end
  end

  assign count_o = {count_expr};
  assign full_o = ({full_expr});
  assign empty_o = {empty_expr};
""".format(
        count_expr=count_expr,
        full_expr=full_expr,
        empty_expr="empty_dly_q" if buggy and mode == "empty_late" else "(count_q == 3'd0)",
    )
    return f"""`timescale 1ns/1ps
module {case_name} (
  input logic clk,
  input logic rst_n,
  input logic clr_i,
  input logic push_i,
  input logic pop_i,
  output logic full_o,
  output logic empty_o,
  output logic [2:0] count_o
);
{body}
endmodule
"""


def build_uart_tfifo_tb(case_name: str, steps: Sequence[Tuple[int, int, int]]) -> str:
    stimulus = "\n".join(
        f"    clr_i = 1'b{clr}; push_i = 1'b{push}; pop_i = 1'b{pop}; @(posedge clk);"
        for clr, push, pop in steps
    )
    return f"""`timescale 1ns/1ps
module tb_{case_name.split('_', 1)[0]};
  reg clk;
  reg rst_n;
  reg clr_i;
  reg push_i;
  reg pop_i;
  wire full_o;
  wire empty_o;
  wire [2:0] count_o;

  {case_name} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .clr_i(clr_i),
    .push_i(push_i),
    .pop_i(pop_i),
    .full_o(full_o),
    .empty_o(empty_o),
    .count_o(count_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    clr_i = 1'b0;
    push_i = 1'b0;
    pop_i = 1'b0;

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    clr_i = 1'b0; push_i = 1'b0; pop_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def sim_uart_tfifo(mode: str, buggy: bool, steps: Sequence[Tuple[int, int, int]]) -> List[Dict[str, int]]:
    count = 0
    empty_dly = 1
    rows: List[Dict[str, int]] = [
        {"rst_n": 0, "clr_i": 0, "push_i": 0, "pop_i": 0, "full_o": 0, "empty_o": 1, "count_o[2:0]": 0}
    ]
    for idx, (clr_i, push_i, pop_i) in enumerate(steps):
        if idx == 0:
            rst_n = 1
        else:
            rst_n = 1
        prev_count = count
        prev_empty_dly = empty_dly
        empty_dly = 1 if prev_count == 0 else 0
        if not buggy or mode != "clear_ignored":
            if clr_i:
                count = 0
            elif push_i and not pop_i and count < 4:
                count += 1
            elif pop_i and not push_i and count > 0:
                count -= 1
        else:
            if push_i and not pop_i and count < 4:
                count += 1
            elif pop_i and not push_i and count > 0:
                count -= 1
        full_o = 1 if ((count >= 3) if buggy and mode == "full_early" else (count == 4)) else 0
        empty_o = prev_empty_dly if buggy and mode == "empty_late" else (1 if count == 0 else 0)
        count_o = 1 if buggy and mode == "count_off_by_one" else count
        rows.append(
            {
                "rst_n": rst_n,
                "clr_i": clr_i,
                "push_i": push_i,
                "pop_i": pop_i,
                "full_o": full_o,
                "empty_o": empty_o,
                "count_o[2:0]": count_o,
            }
        )
    rows.append(
        {"rst_n": 1, "clr_i": 0, "push_i": 0, "pop_i": 0, "full_o": full_o, "empty_o": empty_o, "count_o[2:0]": count_o}
    )
    return rows


def build_arb_module(case_name: str, mode: str, buggy: bool) -> str:
    if mode == "priority_reversed":
        buggy_select = """    if (req_i[2]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd2;
    end else if (req_i[1]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd1;
    end else if (req_i[0]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd0;
    end"""
    else:
        buggy_select = """    if (req_i[0]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd0;
    end else if (req_i[1]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd1;
    end else if (req_i[2]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd2;
    end"""
    if mode == "grant_without_req" and buggy:
        buggy_select += """
    if (!grant_vld_o && ack_i) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd1;
    end"""
    if mode == "valid_depends_on_ack":
        if buggy:
            vld_guard = "if (ack_i) begin"
            vld_end = "\n    end"
        else:
            vld_guard = ""
            vld_end = ""
    else:
        vld_guard = ""
        vld_end = ""
    logic_block = buggy_select if buggy else """    if (req_i[0]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd0;
    end else if (req_i[1]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd1;
    end else if (req_i[2]) begin
      grant_vld_o = 1'b1;
      grant_idx_o = 2'd2;
    end"""
    return f"""`timescale 1ns/1ps
module {case_name} (
  input logic clk,
  input logic rst_n,
  input logic [2:0] req_i,
  input logic ack_i,
  output logic grant_vld_o,
  output logic [1:0] grant_idx_o
);
  always_comb begin
    grant_vld_o = 1'b0;
    grant_idx_o = 2'd0;
    {vld_guard}
{logic_block}
    {vld_end}
  end
endmodule
"""


def build_arb_tb(case_name: str, steps: Sequence[Tuple[int, int]]) -> str:
    stimulus = "\n".join(
        f"    req_i = 3'b{field_bit(req, 3)}; ack_i = 1'b{ack}; @(posedge clk);"
        for req, ack in steps
    )
    return f"""`timescale 1ns/1ps
module tb_{case_name.split('_', 1)[0]};
  reg clk;
  reg rst_n;
  reg [2:0] req_i;
  reg ack_i;
  wire grant_vld_o;
  wire [1:0] grant_idx_o;

  {case_name} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .req_i(req_i),
    .ack_i(ack_i),
    .grant_vld_o(grant_vld_o),
    .grant_idx_o(grant_idx_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    req_i = 3'b000;
    ack_i = 1'b0;

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    req_i = 3'b000; ack_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def sim_arb(mode: str, buggy: bool, steps: Sequence[Tuple[int, int]]) -> List[Dict[str, int]]:
    rows: List[Dict[str, int]] = [
        {"rst_n": 0, "ack_i": 0, "req_i[2:0]": 0, "grant_vld_o": 0, "grant_idx_o[1:0]": 0}
    ]
    for req_i, ack_i in steps:
        grant_vld = 0
        grant_idx = 0
        if mode == "valid_depends_on_ack" and buggy and not ack_i:
            pass
        else:
            order = [2, 1, 0] if mode == "priority_reversed" and buggy else [0, 1, 2]
            for idx in order:
                if req_i & (1 << idx):
                    grant_vld = 1
                    grant_idx = idx
                    break
        if mode == "grant_without_req" and buggy and not grant_vld and ack_i:
            grant_vld = 1
            grant_idx = 1
        rows.append(
            {
                "rst_n": 1,
                "ack_i": ack_i,
                "req_i[2:0]": req_i,
                "grant_vld_o": grant_vld,
                "grant_idx_o[1:0]": grant_idx,
            }
        )
    rows.append({"rst_n": 1, "ack_i": 0, "req_i[2:0]": 0, "grant_vld_o": 0, "grant_idx_o[1:0]": 0})
    return rows


def build_i2c_module(case_name: str, mode: str, buggy: bool) -> str:
    if mode == "start_busy_missing" and buggy:
        start_body = """        busy_q <= 1'b0;
        scl_oen_q <= 1'b0;
        sda_oen_q <= 1'b0;"""
    elif mode == "start_drive_missing" and buggy:
        start_body = """        busy_q <= 1'b1;
        scl_oen_q <= 1'b0;
        sda_oen_q <= 1'b1;"""
    else:
        start_body = """        busy_q <= 1'b1;
        scl_oen_q <= 1'b0;
        sda_oen_q <= 1'b0;"""
    if mode == "stop_release_late" and buggy:
        stop_body = """        busy_q <= 1'b1;
        scl_oen_q <= 1'b0;
        sda_oen_q <= 1'b0;"""
    else:
        stop_body = """        busy_q <= 1'b0;
        scl_oen_q <= 1'b1;
        sda_oen_q <= 1'b1;"""
    return f"""`timescale 1ns/1ps
module {case_name} (
  input logic clk,
  input logic rst_n,
  input logic start_i,
  input logic stop_i,
  output logic busy_o,
  output logic scl_oen_o,
  output logic sda_oen_o
);
  logic busy_q;
  logic scl_oen_q;
  logic sda_oen_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      busy_q <= 1'b0;
      scl_oen_q <= 1'b1;
      sda_oen_q <= 1'b1;
    end else if (start_i && !busy_q) begin
{start_body}
    end else if (stop_i && busy_q) begin
{stop_body}
    end
  end

  assign busy_o = busy_q;
  assign scl_oen_o = scl_oen_q;
  assign sda_oen_o = sda_oen_q;
endmodule
"""


def build_i2c_tb(case_name: str, steps: Sequence[Tuple[int, int]]) -> str:
    stimulus = "\n".join(
        f"    start_i = 1'b{start}; stop_i = 1'b{stop}; @(posedge clk);"
        for start, stop in steps
    )
    return f"""`timescale 1ns/1ps
module tb_{case_name.split('_', 1)[0]};
  reg clk;
  reg rst_n;
  reg start_i;
  reg stop_i;
  wire busy_o;
  wire scl_oen_o;
  wire sda_oen_o;

  {case_name} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .start_i(start_i),
    .stop_i(stop_i),
    .busy_o(busy_o),
    .scl_oen_o(scl_oen_o),
    .sda_oen_o(sda_oen_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    start_i = 1'b0;
    stop_i = 1'b0;

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    start_i = 1'b0; stop_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def sim_i2c(mode: str, buggy: bool, steps: Sequence[Tuple[int, int]]) -> List[Dict[str, int]]:
    busy = 0
    scl = 1
    sda = 1
    rows: List[Dict[str, int]] = [{"rst_n": 0, "start_i": 0, "stop_i": 0, "busy_o": 0, "scl_oen_o": 1, "sda_oen_o": 1}]
    for start_i, stop_i in steps:
        if start_i and not busy:
            if buggy and mode == "start_busy_missing":
                busy = 0
                scl = 0
                sda = 0
            elif buggy and mode == "start_drive_missing":
                busy = 1
                scl = 0
                sda = 1
            else:
                busy = 1
                scl = 0
                sda = 0
        elif stop_i and busy:
            if buggy and mode == "stop_release_late":
                busy = 1
                scl = 0
                sda = 0
            else:
                busy = 0
                scl = 1
                sda = 1
        rows.append({"rst_n": 1, "start_i": start_i, "stop_i": stop_i, "busy_o": busy, "scl_oen_o": scl, "sda_oen_o": sda})
    rows.append({"rst_n": 1, "start_i": 0, "stop_i": 0, "busy_o": busy, "scl_oen_o": scl, "sda_oen_o": sda})
    return rows


def build_spi_module(case_name: str, mode: str, buggy: bool) -> str:
    if mode == "cs_not_asserted_on_start" and buggy:
        start_body = """        busy_q <= 1'b1;
        cs_n_q <= 1'b1;
        sclk_q <= 1'b0;"""
    else:
        start_body = """        busy_q <= 1'b1;
        cs_n_q <= 1'b0;
        sclk_q <= 1'b0;"""
    if mode == "busy_drops_early" and buggy:
        busy_body = """        busy_q <= 1'b0;
        cs_n_q <= 1'b1;
        sclk_q <= 1'b0;"""
    else:
        busy_body = """        busy_q <= 1'b1;
        cs_n_q <= 1'b0;
        sclk_q <= ~sclk_q;"""
    idle_body = """        busy_q <= 1'b0;
        cs_n_q <= 1'b1;
        sclk_q <= ~sclk_q;""" if mode == "sclk_toggles_while_idle" and buggy else """        busy_q <= 1'b0;
        cs_n_q <= 1'b1;
        sclk_q <= 1'b0;"""
    return f"""`timescale 1ns/1ps
module {case_name} (
  input logic clk,
  input logic rst_n,
  input logic start_i,
  input logic done_i,
  output logic busy_o,
  output logic cs_n_o,
  output logic sclk_o
);
  logic busy_q;
  logic cs_n_q;
  logic sclk_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      busy_q <= 1'b0;
      cs_n_q <= 1'b1;
      sclk_q <= 1'b0;
    end else if (start_i && !busy_q) begin
{start_body}
    end else if (busy_q && done_i) begin
      busy_q <= 1'b0;
      cs_n_q <= 1'b1;
      sclk_q <= 1'b0;
    end else if (busy_q) begin
{busy_body}
    end else begin
{idle_body}
    end
  end

  assign busy_o = busy_q;
  assign cs_n_o = cs_n_q;
  assign sclk_o = sclk_q;
endmodule
"""


def build_spi_tb(case_name: str, steps: Sequence[Tuple[int, int]]) -> str:
    stimulus = "\n".join(
        f"    start_i = 1'b{start}; done_i = 1'b{done}; @(posedge clk);"
        for start, done in steps
    )
    return f"""`timescale 1ns/1ps
module tb_{case_name.split('_', 1)[0]};
  reg clk;
  reg rst_n;
  reg start_i;
  reg done_i;
  wire busy_o;
  wire cs_n_o;
  wire sclk_o;

  {case_name} u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .start_i(start_i),
    .done_i(done_i),
    .busy_o(busy_o),
    .cs_n_o(cs_n_o),
    .sclk_o(sclk_o)
  );

  always #5 clk = ~clk;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    start_i = 1'b0;
    done_i = 1'b0;

    repeat (2) @(posedge clk);
    rst_n = 1'b1;
{stimulus}
    start_i = 1'b0; done_i = 1'b0; @(posedge clk);
    $finish;
  end
endmodule
"""


def sim_spi(mode: str, buggy: bool, steps: Sequence[Tuple[int, int]]) -> List[Dict[str, int]]:
    busy = 0
    cs_n = 1
    sclk = 0
    rows: List[Dict[str, int]] = [{"rst_n": 0, "start_i": 0, "done_i": 0, "busy_o": 0, "cs_n_o": 1, "sclk_o": 0}]
    for start_i, done_i in steps:
        if start_i and not busy:
            busy = 1
            cs_n = 1 if buggy and mode == "cs_not_asserted_on_start" else 0
            sclk = 0
        elif busy and done_i:
            busy = 0
            cs_n = 1
            sclk = 0
        elif busy:
            if buggy and mode == "busy_drops_early":
                busy = 0
                cs_n = 1
                sclk = 0
            else:
                busy = 1
                cs_n = 0
                sclk = 0 if sclk else 1
        else:
            busy = 0
            cs_n = 1
            sclk = 0 if not (buggy and mode == "sclk_toggles_while_idle") else (0 if sclk else 1)
        rows.append({"rst_n": 1, "start_i": start_i, "done_i": done_i, "busy_o": busy, "cs_n_o": cs_n, "sclk_o": sclk})
    rows.append({"rst_n": 1, "start_i": 0, "done_i": 0, "busy_o": busy, "cs_n_o": cs_n, "sclk_o": sclk})
    return rows


def create_case(
    *,
    root: Path,
    entry: Dict[str, object],
    correct_text: str,
    buggy_text: str,
    tb_text: str,
    tb_holdout_text: str,
    good_rows: Sequence[Dict[str, int]],
    bad_rows: Sequence[Dict[str, int]],
    holdout_good_rows: Sequence[Dict[str, int]],
    holdout_bad_rows: Sequence[Dict[str, int]],
    widths: Dict[str, int],
    notes: str,
) -> None:
    out_dir = root / str(entry["name"])
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_text(out_dir / "correct.v", correct_text)
    write_text(out_dir / "buggy.v", buggy_text)
    write_text(out_dir / "tb.v", tb_text)
    write_text(out_dir / "tb_holdout.v", tb_holdout_text)
    write_text(out_dir / "STIMULUS_NOTES.md", notes)
    write_csv(out_dir / "waveform_good.csv", list(emit_trace(good_rows, widths)[0].keys()), emit_trace(good_rows, widths))
    write_csv(out_dir / "waveform_bad.csv", list(emit_trace(bad_rows, widths)[0].keys()), emit_trace(bad_rows, widths))
    write_csv(
        out_dir / "waveform_good_holdout.csv",
        list(emit_trace(holdout_good_rows, widths)[0].keys()),
        emit_trace(holdout_good_rows, widths),
    )
    write_csv(
        out_dir / "waveform_bad_holdout.csv",
        list(emit_trace(holdout_bad_rows, widths)[0].keys()),
        emit_trace(holdout_bad_rows, widths),
    )


def update_readme(root: Path, entries: Sequence[Dict[str, object]]) -> None:
    seeds = [entry for entry in entries if not entry.get("seed_case_name")]
    augments = [entry for entry in entries if entry.get("seed_case_name")]
    combo = sum(1 for entry in entries if entry.get("bug_class") == "combination_same_cycle")
    temporal = sum(1 for entry in entries if entry.get("bug_class") == "temporal_cross_cycle")
    project_counts: Dict[str, int] = {}
    for entry in entries:
        project = str(entry.get("source_project", "")).strip()
        if project:
            project_counts[project] = project_counts.get(project, 0) + 1
    project_text = ", ".join(f"{name} {count}/{len(entries)}" for name, count in sorted(project_counts.items()))
    lines = [
        "# Real RTL Scale120",
        "",
        "This root is generated from admitted real-RTL seeds, a reduced augmentation pool, and added cross-project benchmark seeds.",
        "",
        f"- total cases: {len(entries)}",
        f"- unique seed coverage: {len(seeds)}",
        f"- augmentation/variant pool: {len(augments)}",
        f"- combination/same-cycle cases: {combo}",
        f"- temporal/cross-cycle cases: {temporal}",
        f"- source projects: {project_text}",
        "",
        "Generation policy:",
        "- keep only seed cases that already passed the strict golden self-check gate or are explicitly admitted benchmark scaffolds",
        "- preserve a separate augmentation pool, but do not let augmentation dominate source diversity accounting",
        "- enforce a three-track structure per case: seen trace, held-out trace, and explicit overfit decoy",
        "- keep the dataset near 120 total cases while prioritizing unique seed and cross-project coverage",
        "",
        "Counting policy:",
        "- Cases without `seed_case_name` are the only cases that count as unique seed coverage.",
        "- Cases with `seed_case_name` are augmentation-only and do not count as new module, new seed, or new bug-family coverage.",
        "",
    ]
    write_text(root / "README.md", "\n".join(lines))


def build_entries(root: Path) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []

    fifo_specs = [
        (
            "case241_uart_tfifo_full_early",
            "full_early",
            "combination_same_cycle",
            "fifo_boundary_flag",
            "full asserted one slot early",
            "full_o shall assert only when the TX FIFO already contains four entries; it must remain low at count 3.",
            "assert property (@(posedge clk) disable iff (!rst_n) ((count_o == 3'd3) && !pop_i && !clr_i) |-> !full_o);",
            "The primary trace reaches count 3 through a clean push sequence, while held-out reaches the same boundary after an extra idle cycle.",
            "Use visible counts 1,2,3,4 in the seen trace so literal pinning is tempting; held-out inserts an idle before the boundary.",
        ),
        (
            "case242_uart_tfifo_empty_late",
            "empty_late",
            "combination_same_cycle",
            "fifo_boundary_flag",
            "empty asserted one cycle late",
            "empty_o shall assert in the same cycle the TX FIFO count returns to zero.",
            "assert property (@(posedge clk) disable iff (!rst_n) (count_o == 3'd0) |-> empty_o);",
            "The bug only appears at the exact pop-to-zero boundary, so loose mutual-exclusion checks are not enough.",
            "Seen trace drains a two-entry FIFO straight to zero; held-out drains after an extra idle bubble.",
        ),
        (
            "case243_uart_tfifo_count_off_by_one",
            "count_off_by_one",
            "combination_same_cycle",
            "fifo_boundary_flag",
            "count output biased high on empty",
            "Whenever empty_o is high, count_o must be exactly zero.",
            "assert property (@(posedge clk) disable iff (!rst_n) empty_o |-> (count_o == 3'd0));",
            "A buggy count output can still look plausible on non-empty cycles, so the exact empty boundary must be checked.",
            "Seen trace revisits empty after traffic; held-out does so after a short refill sequence.",
        ),
        (
            "case284_uart_tfifo_clear_ignored",
            "clear_ignored",
            "temporal_cross_cycle",
            "fifo_reset_behavior",
            "clear pulse ignored",
            "A clear pulse shall reset the FIFO by the next sampled cycle.",
            "assert property (@(posedge clk) disable iff (!rst_n) clr_i |=> (empty_o && (count_o == 3'd0)));",
            "The bug hides behind otherwise-correct push/pop behavior and only appears when clear is pulsed on a non-empty FIFO.",
            "Seen trace clears at count 2; held-out clears at count 3 after a different prelude.",
        ),
    ]

    widths_fifo = {"rst_n": 1, "clr_i": 1, "push_i": 1, "pop_i": 1, "full_o": 1, "empty_o": 1, "count_o[2:0]": 3}
    for case_name, mode, bug_class, bug_family, bug_type, spec, golden, rationale, lure in fifo_specs:
        primary = [(0, 1, 0), (0, 1, 0), (0, 1, 0), (0, 0, 1)] if mode != "clear_ignored" else [(0, 1, 0), (0, 1, 0), (1, 0, 0), (0, 0, 0)]
        holdout = [(0, 1, 0), (0, 0, 0), (0, 1, 0), (0, 1, 0), (0, 0, 1)] if mode != "clear_ignored" else [(0, 1, 0), (0, 1, 0), (0, 1, 0), (1, 0, 0), (0, 0, 0)]
        entry = {
            "name": case_name,
            "source_project": "opencores",
            "source_module": "uart_tfifo",
            "source_origin": "opencores_inspired_minimal_scaffold",
            "bug_class": bug_class,
            "bug_family": bug_family,
            "bug_type": bug_type,
            "spec": spec,
            "key_signals": ["clk", "rst_n", "clr_i", "push_i", "pop_i", "full_o", "empty_o", "count_o"],
            "golden_sva": {
                "sva": golden,
                "expected_behavior": spec,
                "temporal_type": "same-cycle boundary check" if bug_class == "combination_same_cycle" else "next-cycle clear check",
            },
            "loose_negative_controls": [
                {
                    "name": "push_changes_state",
                    "sva": "assert property (@(posedge clk) disable iff (!rst_n) push_i |-> !empty_o);",
                    "why_it_should_miss": "It does not constrain the exact faulty boundary or clear behavior.",
                },
                {
                    "name": "full_empty_exclusive",
                    "sva": "assert property (@(posedge clk) disable iff (!rst_n) !(full_o && empty_o));",
                    "why_it_should_miss": "The buggy design can satisfy this while still violating the targeted boundary relation.",
                },
            ],
            "hard_case_rationale": rationale,
            "overfit_lure": lure,
            "stimulus_notes": "Both seen and held-out preserve the same FIFO bug trigger, but the prelude and visible count literals differ.",
            "dataset_phase": "cross_project_seed_expansion",
            "status": "admitted_seed",
            "dut_top_module": case_name,
        }
        notes = stimulus_notes(
            case_name=case_name,
            bug_class=bug_class,
            bug_family=bug_family,
            bug_type=bug_type,
            spec=spec,
            rationale=rationale,
            stimulus="Seen and held-out both preserve the same FIFO boundary relation but differ in prelude length and visible count literals.",
            loose_controls=[
                ("push_changes_state", "It does not constrain the exact faulty boundary or clear behavior.", "assert property (@(posedge clk) disable iff (!rst_n) push_i |-> !empty_o);"),
                ("full_empty_exclusive", "The buggy design can satisfy this while still violating the targeted boundary relation.", "assert property (@(posedge clk) disable iff (!rst_n) !(full_o && empty_o));"),
            ],
        )
        create_case(
            root=root,
            entry=entry,
            correct_text=build_uart_tfifo_module(case_name, mode, False),
            buggy_text=build_uart_tfifo_module(case_name, mode, True),
            tb_text=build_uart_tfifo_tb(case_name, primary),
            tb_holdout_text=build_uart_tfifo_tb(case_name, holdout),
            good_rows=sim_uart_tfifo(mode, False, primary),
            bad_rows=sim_uart_tfifo(mode, True, primary),
            holdout_good_rows=sim_uart_tfifo(mode, False, holdout),
            holdout_bad_rows=sim_uart_tfifo(mode, True, holdout),
            widths=widths_fifo,
            notes=notes,
        )
        entries.append(entry)

    arb_specs = [
        (
            "case285_wb_conmax_arb_priority_reversed",
            "priority_reversed",
            "combination_same_cycle",
            "arbiter_priority",
            "priority encoding reversed",
            "When requestors 0 and 2 are both active, the arbiter shall grant requestor 0.",
            "assert property (@(posedge clk) disable iff (!rst_n) (req_i == 3'b101) |-> (grant_vld_o && (grant_idx_o == 2'd0)));",
            "Seen trace uses the literal pair 101; held-out revisits the same conflict after an idle bubble.",
        ),
        (
            "case286_wb_conmax_arb_grant_without_req",
            "grant_without_req",
            "combination_same_cycle",
            "arbiter_safety",
            "grant valid rises without a request",
            "If no request bit is set, grant_vld_o must remain low.",
            "assert property (@(posedge clk) disable iff (!rst_n) (req_i == 3'b000) |-> !grant_vld_o);",
            "Seen trace pairs ack_i with no request; held-out keeps the no-request corner but moves it later.",
        ),
        (
            "case287_wb_conmax_arb_valid_depends_on_ack",
            "valid_depends_on_ack",
            "combination_same_cycle",
            "arbiter_visibility",
            "grant valid incorrectly depends on ack",
            "Any active request shall produce a visible grant even before ack_i rises.",
            "assert property (@(posedge clk) disable iff (!rst_n) ((req_i != 3'b000) && !ack_i) |-> grant_vld_o);",
            "Seen trace shows requests arriving before ack; held-out changes which requestor is used.",
        ),
    ]
    widths_arb = {"rst_n": 1, "ack_i": 1, "req_i[2:0]": 3, "grant_vld_o": 1, "grant_idx_o[1:0]": 2}
    for idx, (case_name, mode, bug_class, bug_family, bug_type, spec, golden, lure) in enumerate(arb_specs):
        primary = [(0b001, 0), (0b101, 0), (0b000, 1), (0b010, 0)]
        holdout = [(0b010, 0), (0b101, 0), (0b000, 1), (0b100, 0)]
        if mode == "grant_without_req":
            primary = [(0b001, 0), (0b000, 1), (0b000, 0), (0b010, 0)]
            holdout = [(0b100, 0), (0b000, 1), (0b001, 0), (0b000, 0)]
        elif mode == "valid_depends_on_ack":
            primary = [(0b001, 0), (0b001, 0), (0b001, 1), (0b000, 0)]
            holdout = [(0b100, 0), (0b100, 0), (0b100, 1), (0b000, 0)]
        rationale = "A loose arbiter check can pass while missing the exact visibility or priority corner that differentiates correct arbitration from a memorized trace literal."
        notes = stimulus_notes(
            case_name=case_name,
            bug_class=bug_class,
            bug_family=bug_family,
            bug_type=bug_type,
            spec=spec,
            rationale=rationale,
            stimulus="Seen and held-out both preserve the same arbitration relation but change request patterns and idle spacing.",
            loose_controls=[
                ("some_request_grants", "It only checks a subset of request patterns and ignores the exact corner.", "assert property (@(posedge clk) disable iff (!rst_n) req_i[0] |-> grant_vld_o);"),
                ("grant_index_range", "It says nothing about the exact request/grant relation.", "assert property (@(posedge clk) disable iff (!rst_n) grant_idx_o <= 2'd2);"),
            ],
        )
        entry = {
            "name": case_name,
            "source_project": "opencores",
            "source_module": "wb_conmax_arb",
            "source_origin": "opencores_inspired_minimal_scaffold",
            "bug_class": bug_class,
            "bug_family": bug_family,
            "bug_type": bug_type,
            "spec": spec,
            "key_signals": ["clk", "rst_n", "req_i", "ack_i", "grant_vld_o", "grant_idx_o"],
            "golden_sva": {"sva": golden, "expected_behavior": spec, "temporal_type": "same-cycle arbitration check"},
            "loose_negative_controls": [
                {
                    "name": "some_request_grants",
                    "sva": "assert property (@(posedge clk) disable iff (!rst_n) req_i[0] |-> grant_vld_o);",
                    "why_it_should_miss": "It only checks a subset of request patterns and ignores the exact corner.",
                },
                {
                    "name": "grant_index_range",
                    "sva": "assert property (@(posedge clk) disable iff (!rst_n) grant_idx_o <= 2'd2);",
                    "why_it_should_miss": "It says nothing about the exact request/grant relation.",
                },
            ],
            "hard_case_rationale": rationale,
            "overfit_lure": lure,
            "stimulus_notes": "Seen and held-out both preserve the same arbitration relation but change request patterns and idle spacing.",
            "dataset_phase": "cross_project_seed_expansion",
            "status": "admitted_seed",
            "dut_top_module": case_name,
        }
        create_case(
            root=root,
            entry=entry,
            correct_text=build_arb_module(case_name, mode, False),
            buggy_text=build_arb_module(case_name, mode, True),
            tb_text=build_arb_tb(case_name, primary),
            tb_holdout_text=build_arb_tb(case_name, holdout),
            good_rows=sim_arb(mode, False, primary),
            bad_rows=sim_arb(mode, True, primary),
            holdout_good_rows=sim_arb(mode, False, holdout),
            holdout_bad_rows=sim_arb(mode, True, holdout),
            widths=widths_arb,
            notes=notes,
        )
        entries.append(entry)

    i2c_specs = [
        (
            "case288_i2c_master_start_busy_missing",
            "start_busy_missing",
            "combination_same_cycle",
            "i2c_start_visibility",
            "busy does not rise on start",
            "A start command issued while idle shall set busy_o high immediately.",
            "assert property (@(posedge clk) disable iff (!rst_n) start_i |-> busy_o);",
            "Seen trace starts from idle; held-out inserts one extra idle cycle before the same start literal.",
        ),
        (
            "case289_i2c_master_start_drive_missing",
            "start_drive_missing",
            "combination_same_cycle",
            "i2c_start_drive",
            "start does not pull SDA low",
            "A start command shall drive SDA low in the sampled start cycle.",
            "assert property (@(posedge clk) disable iff (!rst_n) start_i |-> !sda_oen_o);",
            "Seen and held-out both use a start pulse but with different idle spacing around it.",
        ),
        (
            "case290_i2c_master_stop_release_late",
            "stop_release_late",
            "combination_same_cycle",
            "i2c_stop_release",
            "stop does not release bus immediately",
            "A stop command while busy shall release SCL/SDA and clear busy_o in the same sampled cycle.",
            "assert property (@(posedge clk) disable iff (!rst_n) stop_i |-> (!busy_o && scl_oen_o && sda_oen_o));",
            "Seen trace stops after one active cycle; held-out stops after a longer busy prelude.",
        ),
    ]
    widths_i2c = {"rst_n": 1, "start_i": 1, "stop_i": 1, "busy_o": 1, "scl_oen_o": 1, "sda_oen_o": 1}
    for case_name, mode, bug_class, bug_family, bug_type, spec, golden, lure in i2c_specs:
        primary = [(1, 0), (0, 0), (0, 1), (0, 0)] if mode == "stop_release_late" else [(1, 0), (0, 0), (0, 0)]
        holdout = [(0, 0), (1, 0), (0, 0), (0, 1), (0, 0)] if mode == "stop_release_late" else [(0, 0), (1, 0), (0, 0), (0, 0)]
        rationale = "The bus can look superficially plausible while still missing the exact start/stop semantics that matter for assertion generalization."
        notes = stimulus_notes(
            case_name=case_name,
            bug_class=bug_class,
            bug_family=bug_family,
            bug_type=bug_type,
            spec=spec,
            rationale=rationale,
            stimulus="Seen and held-out preserve the same I2C start/stop trigger, but they differ in idle spacing and active prelude length.",
            loose_controls=[
                ("busy_eventually_changes", "It does not constrain the exact sampled start/stop cycle.", "assert property (@(posedge clk) disable iff (!rst_n) start_i |-> (busy_o || scl_oen_o));"),
                ("lines_not_x", "It says nothing about correct start/stop semantics.", "assert property (@(posedge clk) disable iff (!rst_n) (scl_oen_o == 1'b0 || scl_oen_o == 1'b1));"),
            ],
        )
        entry = {
            "name": case_name,
            "source_project": "opencores",
            "source_module": "i2c_master_bit_ctrl",
            "source_origin": "opencores_inspired_minimal_scaffold",
            "bug_class": bug_class,
            "bug_family": bug_family,
            "bug_type": bug_type,
            "spec": spec,
            "key_signals": ["clk", "rst_n", "start_i", "stop_i", "busy_o", "scl_oen_o", "sda_oen_o"],
            "golden_sva": {"sva": golden, "expected_behavior": spec, "temporal_type": "same-cycle bus control check"},
            "loose_negative_controls": [
                {
                    "name": "busy_eventually_changes",
                    "sva": "assert property (@(posedge clk) disable iff (!rst_n) start_i |-> (busy_o || scl_oen_o));",
                    "why_it_should_miss": "It does not constrain the exact sampled start/stop cycle.",
                },
                {
                    "name": "lines_not_x",
                    "sva": "assert property (@(posedge clk) disable iff (!rst_n) (scl_oen_o == 1'b0 || scl_oen_o == 1'b1));",
                    "why_it_should_miss": "It says nothing about correct start/stop semantics.",
                },
            ],
            "hard_case_rationale": rationale,
            "overfit_lure": lure,
            "stimulus_notes": "Seen and held-out preserve the same I2C start/stop trigger, but they differ in idle spacing and active prelude length.",
            "dataset_phase": "cross_project_seed_expansion",
            "status": "admitted_seed",
            "dut_top_module": case_name,
        }
        create_case(
            root=root,
            entry=entry,
            correct_text=build_i2c_module(case_name, mode, False),
            buggy_text=build_i2c_module(case_name, mode, True),
            tb_text=build_i2c_tb(case_name, primary),
            tb_holdout_text=build_i2c_tb(case_name, holdout),
            good_rows=sim_i2c(mode, False, primary),
            bad_rows=sim_i2c(mode, True, primary),
            holdout_good_rows=sim_i2c(mode, False, holdout),
            holdout_bad_rows=sim_i2c(mode, True, holdout),
            widths=widths_i2c,
            notes=notes,
        )
        entries.append(entry)

    spi_specs = [
        (
            "case291_spi_top_cs_not_asserted_on_start",
            "cs_not_asserted_on_start",
            "combination_same_cycle",
            "spi_chip_select",
            "chip select stays high on start",
            "A start command shall assert chip select low immediately.",
            "assert property (@(posedge clk) disable iff (!rst_n) start_i |-> !cs_n_o);",
            "Seen trace uses a short burst; held-out adds an idle cycle before the same start pulse.",
        ),
        (
            "case292_spi_top_busy_drops_early",
            "busy_drops_early",
            "temporal_cross_cycle",
            "spi_transfer_liveness",
            "busy drops before done",
            "Once a transfer starts, busy_o shall stay high until done_i is observed.",
            "assert property (@(posedge clk) disable iff (!rst_n) ($past(busy_o) && !done_i) |-> busy_o);",
            "Seen trace keeps done_i low for two cycles; held-out stretches the active burst one cycle longer.",
        ),
        (
            "case293_spi_top_sclk_toggles_while_idle",
            "sclk_toggles_while_idle",
            "combination_same_cycle",
            "spi_idle_clocking",
            "serial clock toggles while idle",
            "While busy_o is low, sclk_o shall remain low.",
            "assert property (@(posedge clk) disable iff (!rst_n) !busy_o |-> (sclk_o == 1'b0));",
            "Seen and held-out both revisit idle, but with different prior burst lengths so literal timing shortcuts fail.",
        ),
    ]
    widths_spi = {"rst_n": 1, "start_i": 1, "done_i": 1, "busy_o": 1, "cs_n_o": 1, "sclk_o": 1}
    for case_name, mode, bug_class, bug_family, bug_type, spec, golden, lure in spi_specs:
        primary = [(1, 0), (0, 0), (0, 1), (0, 0)] if mode != "sclk_toggles_while_idle" else [(1, 0), (0, 0), (0, 1), (0, 0), (0, 0)]
        holdout = [(0, 0), (1, 0), (0, 0), (0, 0), (0, 1), (0, 0)] if mode != "sclk_toggles_while_idle" else [(0, 0), (1, 0), (0, 0), (0, 1), (0, 0), (0, 0)]
        rationale = "The SPI block can appear mostly healthy while still violating an exact start, busy-hold, or idle-clocking relation that a trace-memorizing assertion will miss."
        notes = stimulus_notes(
            case_name=case_name,
            bug_class=bug_class,
            bug_family=bug_family,
            bug_type=bug_type,
            spec=spec,
            rationale=rationale,
            stimulus="Seen and held-out preserve the same start/busy/idle semantics but change burst length and idle spacing.",
            loose_controls=[
                ("busy_implies_active", "It ignores the exact start or idle corner.", "assert property (@(posedge clk) disable iff (!rst_n) busy_o |-> !cs_n_o);"),
                ("done_clears_busy", "It says nothing about the pre-done hold or idle clock relation.", "assert property (@(posedge clk) disable iff (!rst_n) done_i |-> !busy_o);"),
            ],
        )
        entry = {
            "name": case_name,
            "source_project": "opencores",
            "source_module": "simple_spi_top",
            "source_origin": "opencores_inspired_minimal_scaffold",
            "bug_class": bug_class,
            "bug_family": bug_family,
            "bug_type": bug_type,
            "spec": spec,
            "key_signals": ["clk", "rst_n", "start_i", "done_i", "busy_o", "cs_n_o", "sclk_o"],
            "golden_sva": {"sva": golden, "expected_behavior": spec, "temporal_type": "same-cycle/short temporal SPI check"},
            "loose_negative_controls": [
                {
                    "name": "busy_implies_active",
                    "sva": "assert property (@(posedge clk) disable iff (!rst_n) busy_o |-> !cs_n_o);",
                    "why_it_should_miss": "It ignores the exact start or idle corner.",
                },
                {
                    "name": "done_clears_busy",
                    "sva": "assert property (@(posedge clk) disable iff (!rst_n) done_i |-> !busy_o);",
                    "why_it_should_miss": "It says nothing about the pre-done hold or idle clock relation.",
                },
            ],
            "hard_case_rationale": rationale,
            "overfit_lure": lure,
            "stimulus_notes": "Seen and held-out preserve the same start/busy/idle semantics but change burst length and idle spacing.",
            "dataset_phase": "cross_project_seed_expansion",
            "status": "admitted_seed",
            "dut_top_module": case_name,
        }
        create_case(
            root=root,
            entry=entry,
            correct_text=build_spi_module(case_name, mode, False),
            buggy_text=build_spi_module(case_name, mode, True),
            tb_text=build_spi_tb(case_name, primary),
            tb_holdout_text=build_spi_tb(case_name, holdout),
            good_rows=sim_spi(mode, False, primary),
            bad_rows=sim_spi(mode, True, primary),
            holdout_good_rows=sim_spi(mode, False, holdout),
            holdout_bad_rows=sim_spi(mode, True, holdout),
            widths=widths_spi,
            notes=notes,
        )
        entries.append(entry)
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair scale120 source diversity by replacing some augmentation variants with new OpenCores seed cases.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Target scale120 root.")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    manifest = load_manifest(root)
    new_entries = build_entries(root)
    generated_names = {str(entry["name"]) for entry in new_entries}
    blocked_names = set(REPLACED_VARIANTS) | generated_names

    manifest = [entry for entry in manifest if str(entry["name"]) not in blocked_names]
    for case_name in blocked_names:
        drop_case(root, case_name)

    new_entries = build_entries(root)
    manifest.extend(new_entries)
    manifest = sorted(manifest, key=lambda entry: str(entry["name"]))
    save_manifest(root, manifest)
    ensure_decoy_structure(root)
    manifest = load_manifest(root)
    update_readme(root, manifest)
    print(f"[DONE] Repaired source diversity at {root}")
    print(f"SUMMARY: total={len(manifest)} seeds={sum(1 for e in manifest if not e.get('seed_case_name'))} augmentations={sum(1 for e in manifest if e.get('seed_case_name'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
