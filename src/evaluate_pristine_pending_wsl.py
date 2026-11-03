#!/usr/bin/env python3
"""Evaluate the sealed pristine16 candidate file directly inside WSL.

This script deliberately uses the real case testbenches for primary and held-out
stimuli.  It does not invoke wsl.exe and it does not rewrite unsupported SVA
operators into a different property: unsupported procedural constructs are
reported as compile failures.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO / "rtl_cases_real_scale210_independent"
DEFAULT_EXPERIMENT = REPO / "outputs/pristine_trace_router_v1/dispatch/generated"
KEYS = ("model_label", "case_id", "method", "candidate_index")
COMBINATIONAL_CASES = {439, 440, 441, 442, 443}
UNSUPPORTED_PROCEDURAL = re.compile(
    r"##|\$rose\s*\(|\$fell\s*\(|\$changed\s*\(|\$stable\s*\(|\$past\s*\(|"
    r"\bthroughout\b|\buntil(?:_with)?\b|\bwithin\b|\bs_until\b",
    re.I,
)


def case_number(case_id: str) -> int:
    match = re.match(r"case(\d+)_", case_id)
    if not match:
        raise ValueError(f"Invalid case id: {case_id}")
    return int(match.group(1))


def parse_assertion(text: str) -> tuple[str, str, str, str, str]:
    src = text.strip()
    match = re.match(
        r"assert\s+property\s*\(\s*@\(posedge\s+([^\)]+)\)\s*"
        r"disable\s+iff\s*\((.*?)\)\s*(.*)\)\s*;\s*$",
        src,
        re.I | re.S,
    )
    if not match:
        raise ValueError("unsupported assertion wrapper")
    clock, disable, body = (part.strip() for part in match.groups())
    found = [(body.find(op), op) for op in ("|->", "|=>") if body.find(op) >= 0]
    if len(found) != 1:
        raise ValueError("candidate must contain exactly one implication")
    pos, implication = found[0]
    ant, cons = body[:pos].strip(), body[pos + 3 :].strip()
    for value_name, value in (("antecedent", ant), ("consequent", cons)):
        while value.startswith("(") and value.endswith(")"):
            value = value[1:-1].strip()
        if value_name == "antecedent":
            ant = value
        else:
            cons = value
    if UNSUPPORTED_PROCEDURAL.search(ant) or UNSUPPORTED_PROCEDURAL.search(cons):
        raise ValueError("unsupported temporal/sample operator in procedural checker")
    return clock, disable, ant, implication, cons


def signal_names(case_dir: Path) -> list[str]:
    path = case_dir / "waveform_good.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        headers = next(csv.reader(handle))
    names = []
    for raw in headers:
        if raw == "time_ps":
            continue
        base = raw.split("[", 1)[0]
        if base and base not in names:
            names.append(base)
    return names


def aliases(case_id: str) -> dict[str, str]:
    num = case_number(case_id)
    if num in COMBINATIONAL_CASES:
        return {"clk": "sample_clk", "rst_n": "1'b1"}
    if num in {415, 416}:
        return {"clk": "tb.clk_i", "rst_n": "tb.rst_ni"}
    if num in {417, 418}:
        return {"clk": "tb.clks_i[0]", "rst_n": "tb.async_rstn_i"}
    if num in {421, 425, 426, 449}:
        # The AXIS designs use active-high rst.  A generated canonical rst_n
        # therefore aliases to its complement, preserving disable iff (!rst_n).
        return {"clk": "tb.clk", "rst_n": "(~tb.rst)"}
    return {}


def qualify(expr: str, names: list[str], alias: dict[str, str]) -> str:
    replacements = {name: f"tb.{name}" for name in names}
    replacements.update(alias)
    out = expr
    for name in sorted(replacements, key=len, reverse=True):
        out = re.sub(rf"(?<![A-Za-z0-9_$\.]){re.escape(name)}(?![A-Za-z0-9_$])", replacements[name], out)
    return out


def qualify_clock(clock: str, names: list[str], alias: dict[str, str]) -> str:
    return qualify(clock, names, alias)


def checker(case_id: str, assertion: str, names: list[str]) -> str:
    clock, disable, ant, implication, cons = parse_assertion(assertion)
    alias = aliases(case_id)
    clock_q = qualify_clock(clock, names, alias)
    disable_q, ant_q, cons_q = (qualify(x, names, alias) for x in (disable, ant, cons))
    synthetic = case_number(case_id) in COMBINATIONAL_CASES and clock.strip() == "clk"
    sample_decl = "  reg sample_clk = 1'b0; always #1 sample_clk = ~sample_clk;\n" if synthetic else ""
    if implication == "|->":
        failure = f"if (({ant_q}) && !(({cons_q}))) fail_hits = fail_hits + 1;"
    else:
        failure = f"if (ant_d && !(({cons_q}))) fail_hits = fail_hits + 1;"
    return f"""module pristine_candidate_checker;
  integer ant_hits = 0;
  integer fail_hits = 0;
  reg ant_d = 1'b0;
{sample_decl}  always @(posedge {clock_q}) begin
    if (({disable_q})) begin
      ant_d <= 1'b0;
    end else begin
      if (({ant_q})) ant_hits = ant_hits + 1;
      {failure}
      ant_d <= ({ant_q});
    end
  end
  final $display("PRISTINE_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
endmodule
"""


def compile_command(case_id: str, rtl: Path, tb: Path, checker_path: Path, simv: Path) -> list[str]:
    cmd = [
        "iverilog", "-g2012", "-gno-assertions", "-DSYNTHESIS",
        "-DCOMMON_CELLS_ASSERTS_OFF", "-i",
    ]
    if case_number(case_id) in {417, 418}:
        cmd.append("-DCC_CLK_MUX_TB_DEPS")
    for inc in (
        tb.parent,
        REPO / "external/common_cells/include",
        REPO / "external/common_cells/src",
        REPO / "external/opentitan",
        REPO / "external/opentitan/hw/ip/prim/rtl",
        REPO / "external/verilog-axis/rtl",
    ):
        cmd += ["-I", str(inc)]
    cmd += [
        "-o", str(simv),
        str(REPO / "rtl_cases/iverilog_compat/cc_pkg_iverilog.sv"),
        str(REPO / "rtl_cases/iverilog_compat/cc_clk_mux_tb_deps.sv"),
        str(REPO / "external/opentitan/hw/ip/prim/rtl/prim_util_pkg.sv"),
        str(REPO / "external/opentitan/hw/ip/prim/rtl/prim_count_pkg.sv"),
        str(rtl), str(tb), str(checker_path),
    ]
    return cmd


def run_one(case_id: str, rtl: Path, tb: Path, checker_path: Path, build: Path) -> dict:
    build.mkdir(parents=True, exist_ok=True)
    simv = build / "simv.out"
    comp = subprocess.run(compile_command(case_id, rtl, tb, checker_path, simv), text=True, capture_output=True)
    (build / "compile.stdout.txt").write_text(comp.stdout, encoding="utf-8")
    (build / "compile.stderr.txt").write_text(comp.stderr, encoding="utf-8")
    if comp.returncode:
        return {"compile_ok": False, "sim_ok": False, "ant_hits": 0, "fail_hits": 0}
    sim = subprocess.run(["vvp", str(simv), "+VCD=" + str(build / "wave.vcd")], text=True, capture_output=True)
    (build / "sim.stdout.txt").write_text(sim.stdout, encoding="utf-8")
    (build / "sim.stderr.txt").write_text(sim.stderr, encoding="utf-8")
    metric = re.search(r"PRISTINE_METRIC ant_hits=(\d+) fail_hits=(\d+)", sim.stdout + "\n" + sim.stderr)
    return {
        "compile_ok": True,
        "sim_ok": sim.returncode == 0 and metric is not None,
        "ant_hits": int(metric.group(1)) if metric else 0,
        "fail_hits": int(metric.group(2)) if metric else 0,
    }


def rejected(reason: str) -> dict:
    return {
        "compile_ok": False, "correct_pass": False, "buggy_fail": False,
        "antecedent_hit": False, "non_vacuous": False,
        "heldout_correct_pass": False, "heldout_buggy_fail": False,
        "heldout_antecedent_hit": False, "heldout_non_vacuous": False,
        "trace_overfit": False, "seen_good_ant_hits": 0, "seen_bad_ant_hits": 0,
        "heldout_good_ant_hits": 0, "heldout_bad_ant_hits": 0,
        "seen_good_fail_hits": 0, "seen_bad_fail_hits": 0,
        "heldout_good_fail_hits": 0, "heldout_bad_fail_hits": 0,
        "evaluator_reason": reason,
    }


def evaluate(row: dict, root: Path, runtime: Path) -> dict:
    case_id = row["case_id"]
    case_dir = root / case_id
    candidate_dir = runtime / row["model_label"] / case_id / row["method"] / f"cand_{int(row['candidate_index']):02d}"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    checker_path = candidate_dir / "candidate_checker.sv"
    try:
        checker_path.write_text(checker(case_id, row["assertion_text"], signal_names(case_dir)), encoding="utf-8")
    except ValueError as exc:
        checker_path.write_text("// rejected without semantic rewrite: " + str(exc) + "\n", encoding="utf-8")
        return rejected(str(exc))
    runs = {
        "seen_good": run_one(case_id, case_dir / "correct.v", case_dir / "tb.v", checker_path, candidate_dir / "seen_good"),
        "seen_bad": run_one(case_id, case_dir / "buggy.v", case_dir / "tb.v", checker_path, candidate_dir / "seen_bad"),
        "holdout_good": run_one(case_id, case_dir / "correct.v", case_dir / "tb_holdout.v", checker_path, candidate_dir / "holdout_good"),
        "holdout_bad": run_one(case_id, case_dir / "buggy.v", case_dir / "tb_holdout.v", checker_path, candidate_dir / "holdout_bad"),
    }
    compile_ok = all(x["compile_ok"] and x["sim_ok"] for x in runs.values())
    sg, sb, hg, hb = (runs[k] for k in ("seen_good", "seen_bad", "holdout_good", "holdout_bad"))
    correct_pass = compile_ok and sg["fail_hits"] == 0
    buggy_fail = compile_ok and sb["fail_hits"] > 0
    held_correct = compile_ok and hg["fail_hits"] == 0
    held_buggy = compile_ok and hb["fail_hits"] > 0
    result = {
        "compile_ok": compile_ok, "correct_pass": correct_pass, "buggy_fail": buggy_fail,
        "antecedent_hit": compile_ok and sb["ant_hits"] > 0,
        "non_vacuous": compile_ok and sb["ant_hits"] > 0,
        "heldout_correct_pass": held_correct, "heldout_buggy_fail": held_buggy,
        "heldout_antecedent_hit": compile_ok and hb["ant_hits"] > 0,
        "heldout_non_vacuous": compile_ok and hb["ant_hits"] > 0,
        "trace_overfit": compile_ok and correct_pass and buggy_fail and not (held_correct and held_buggy and hb["ant_hits"] > 0),
        "seen_good_ant_hits": sg["ant_hits"], "seen_bad_ant_hits": sb["ant_hits"],
        "heldout_good_ant_hits": hg["ant_hits"], "heldout_bad_ant_hits": hb["ant_hits"],
        "seen_good_fail_hits": sg["fail_hits"], "seen_bad_fail_hits": sb["fail_hits"],
        "heldout_good_fail_hits": hg["fail_hits"], "heldout_bad_fail_hits": hb["fail_hits"],
        "evaluator_reason": "",
    }
    return result


def classify(row: dict) -> tuple[str, str]:
    if not row["compile_ok"]:
        return "compile_fail", row.get("evaluator_reason") or "iverilog/vvp failed; see candidate runtime logs"
    if not row["correct_pass"]:
        return "rejects_correct", "candidate fails on primary correct RTL"
    if not row["antecedent_hit"]:
        return "vacuous", "antecedent has zero hits on primary buggy RTL"
    if not row["buggy_fail"]:
        return "misses_bug", "candidate has no failure on primary buggy RTL"
    if not row["heldout_correct_pass"]:
        return "heldout_rejects_correct", "candidate fails on held-out correct RTL"
    if not row["heldout_antecedent_hit"]:
        return "heldout_vacuous", "antecedent has zero hits on held-out buggy RTL"
    if not row["heldout_buggy_fail"]:
        return "heldout_misses_bug", "candidate has no failure on held-out buggy RTL"
    return "success", "passes correct and fails buggy on primary and held-out stimuli"


def literal_hardcoding(text: str) -> bool:
    for token in re.findall(r"\b\d+'[bdho][0-9a-fA-F_xzXZ?]+\b|\b\d+\b", text):
        if token.lower() not in {"0", "1", "1'b0", "1'b1", "1'd0", "1'd1", "1'h0", "1'h1"}:
            return True
    return False


def atomic_write(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--experiment-dir", default=str(DEFAULT_EXPERIMENT))
    parser.add_argument("--max-candidates", type=int, default=0)
    args = parser.parse_args()
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        raise SystemExit("ERROR: run inside WSL with iverilog and vvp on PATH")
    root, experiment = Path(args.root).resolve(), Path(args.experiment_dir).resolve()
    pending_path = experiment / "pending_candidates.csv"
    results_path = experiment / "multi_model_results_raw.csv"
    with pending_path.open(encoding="utf-8-sig", newline="") as handle:
        pending = list(csv.DictReader(handle))
    existing: list[dict] = []
    if results_path.exists():
        with results_path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
    by_key = {tuple(str(row.get(k, "")) for k in KEYS): row for row in existing}
    remaining = [row for row in pending if tuple(row[k] for k in KEYS) not in by_key]
    if args.max_candidates:
        remaining = remaining[: args.max_candidates]
    if not remaining:
        print(f"No pending candidates remain ({len(by_key)}/{len(pending)} complete).")
        return
    for idx, pending_row in enumerate(remaining, 1):
        result = evaluate(pending_row, root, experiment / "runtime")
        row = {k: v for k, v in pending_row.items() if k != "evaluation_status"}
        row.update(result)
        row["antecedent_hit_buggy"] = row["antecedent_hit"]
        row["non_vacuous_buggy"] = row["non_vacuous"]
        row["literal_hardcoding"] = literal_hardcoding(row["assertion_text"])
        row["semantic_reasonable"] = not row["literal_hardcoding"]
        row["semantic_reason"] = (
            "Heuristic: contains a nontrivial literal."
            if row["literal_hardcoding"] else
            "Heuristic: no nontrivial literal-specific hardcoding detected."
        )
        mode, reason = classify(row)
        row["failure_mode"], row["failure_reason"] = mode, reason
        row["use_property_compile_mode"] = False
        key = tuple(str(row[k]) for k in KEYS)
        by_key[key] = row
        atomic_write(results_path, list(by_key.values()))
        print(f"[{idx}/{len(remaining)}] {row['model_label']} {row['case_id']} {row['method']} c{row['candidate_index']} -> {mode}")
    print(f"Wrote {len(by_key)}/{len(pending)} rows: {results_path}")


if __name__ == "__main__":
    main()
