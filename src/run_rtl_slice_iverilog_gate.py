#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

MODULE_RE = re.compile(r"(?m)^module\s+([A-Za-z_][A-Za-z0-9_]*)\b")
MODULE_BLOCK_RE = re.compile(r"(?ms)^module\s+[A-Za-z_][A-Za-z0-9_]*\b.*?^endmodule\b")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_slice(text: str) -> str:
    match = MODULE_BLOCK_RE.search(text)
    if not match:
        raise ValueError("slice is not a closed module")
    return match.group(0).strip() + "\n"


def run_command(command: list[str], log_path: Path, timeout: int) -> tuple[bool, int]:
    try:
        result = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        output = result.stdout
        return_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + f"\nTIMEOUT after {timeout}s\n"
        return_code = 124
    log_path.write_text(output, encoding="utf-8")
    return return_code == 0, return_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent Icarus parse/elaboration gate for the fixed slice audit sample.")
    parser.add_argument("--prompt-log", type=Path, default=Path("outputs/rtl_context_slice_audit20/dryrun_v3/multi_model_prompt_log.csv"))
    parser.add_argument("--sample", type=Path, default=Path("outputs/rtl_context_slice_audit20/sample.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/rtl_context_slice_audit20/iverilog_gate"))
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if not shutil.which("iverilog"):
        raise SystemExit("ERROR: iverilog not found; run this gate inside WSL")

    sample = json.loads(args.sample.read_text(encoding="utf-8"))
    case_ids = list(sample["cases"])
    if len(case_ids) != 20 or len(set(case_ids)) != 20:
        raise SystemExit("sample.json must contain exactly 20 unique cases")
    with args.prompt_log.open(encoding="utf-8-sig", newline="") as handle:
        prompt_rows = [
            row for row in csv.DictReader(handle)
            if row.get("method") == "spec_rtl_signal_list_small_slice"
            and row.get("case_id") in set(case_ids)
        ]
    # The slice is model-independent. Prefer GPT if duplicate model rows exist.
    model_rank = {"GPT": 0, "Claude": 1}
    selected_rows: dict[str, dict[str, str]] = {}
    for row in sorted(
        prompt_rows,
        key=lambda item: (
            str(item.get("case_id", "")),
            model_rank.get(str(item.get("model_label", "")), 9),
        ),
    ):
        selected_rows.setdefault(str(row["case_id"]), row)
    if set(selected_rows) != set(case_ids):
        missing = sorted(set(case_ids) - set(selected_rows))
        raise SystemExit(f"missing small-slice rows: {missing}")

    output_dir = args.output_dir.resolve()
    work = output_dir / "work"
    logs = output_dir / "logs"
    work.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    for stale in [*work.glob("*.slice.sv"), *logs.glob("*.log")]:
        stale.unlink()
    repo = Path(__file__).resolve().parents[1]
    dependency_candidates = [
        repo / "external/opentitan/hw/ip/prim/rtl/prim_assert.sv",
        repo / "external/opentitan/hw/ip/prim/rtl/prim_util_pkg.sv",
        repo / "external/opentitan/hw/ip/prim/rtl/prim_count_pkg.sv",
        repo / "rtl_cases/iverilog_compat/cc_pkg_iverilog.sv",
    ]
    dependencies = [str(path) for path in dependency_candidates if path.is_file()]
    include_dirs = [
        repo / "external/opentitan/hw/ip/prim/rtl",
        repo / "external/common_cells/include",
        repo / "external/common_cells/src",
        repo / "external/verilog-axis/rtl",
    ]
    include_args = [part for path in include_dirs for part in ("-I", str(path))]

    rows: list[dict[str, object]] = []
    for index, case_id in enumerate(case_ids, 1):
        source_row = selected_rows[case_id]
        try:
            code = extract_slice(str(source_row["rtl_context_text"]))
            module = MODULE_RE.search(code).group(1)  # type: ignore[union-attr]
            slice_path = work / f"{case_id}.slice.sv"
            slice_path.write_text(code, encoding="utf-8")
            parse_ok, parse_rc = run_command(
                ["iverilog", "-g2012", "-tnull", "-i", "-DSYNTHESIS", *include_args, *dependencies, str(slice_path)],
                logs / f"{case_id}.parse.log", args.timeout,
            )
            elaborate_ok, elaborate_rc = run_command(
                ["iverilog", "-g2012", "-tnull", "-i", "-DSYNTHESIS", "-s", module, *include_args, *dependencies, str(slice_path)],
                logs / f"{case_id}.elaborate.log", args.timeout,
            )
            error = ""
        except (OSError, ValueError) as exc:
            module = ""
            slice_path = work / f"{case_id}.slice.sv"
            parse_ok = elaborate_ok = False
            parse_rc = elaborate_rc = 2
            error = str(exc)
            (logs / f"{case_id}.parse.log").write_text(error + "\n", encoding="utf-8")
            (logs / f"{case_id}.elaborate.log").write_text(error + "\n", encoding="utf-8")
        rows.append({
            "case_id": case_id,
            "parent_bug_id": case_id,
            "sample_seed": sample.get("seed"),
            "source_model_row": source_row["model_label"],
            "module": module,
            "slice_sha256": sha256(slice_path) if slice_path.is_file() else "",
            "parse_ok": parse_ok,
            "parse_returncode": parse_rc,
            "elaboration_ok": elaborate_ok,
            "elaboration_returncode": elaborate_rc,
            "gate_ok": parse_ok and elaborate_ok,
            "error": error,
        })
        print(f"[{index:02d}/20] {'PASS' if rows[-1]['gate_ok'] else 'FAIL'} {case_id}")

    report = output_dir / "iverilog_slice_gate.csv"
    with report.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema_version": 1,
        "tool": subprocess.run(["iverilog", "-V"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.splitlines()[0],
        "sample_seed": sample.get("seed"),
        "sample_case_count": len(rows),
        "parse_pass_count": sum(bool(row["parse_ok"]) for row in rows),
        "elaboration_pass_count": sum(bool(row["elaboration_ok"]) for row in rows),
        "gate_pass_count": sum(bool(row["gate_ok"]) for row in rows),
        "all_pass": all(bool(row["gate_ok"]) for row in rows),
        "prompt_log_sha256": sha256(args.prompt_log),
        "sample_sha256": sha256(args.sample),
        "report_sha256": sha256(report),
        "gate_definition": "actual small-slice module parses and elaborates as the selected top under Icarus; only vendored package/include dependencies are supplied",
    }
    (output_dir / "iverilog_slice_gate_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    raise SystemExit(0 if summary["all_pass"] else 1)


if __name__ == "__main__":
    main()
