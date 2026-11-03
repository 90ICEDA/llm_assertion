from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT1 = ROOT / "outputs/behavioral_preference_pilot_v1"
PILOT2 = ROOT / "outputs/behavioral_preference_pilot_v2"
SOURCE = PILOT2 / "ast_smoke_v2"
OUT = PILOT2 / "ast_smoke_v2_validation"
KEYS = ("antecedent_signal", "antecedent_polarity", "consequent_signal", "implication", "relation")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render(ast: dict, clock: str | None, reset: str | None) -> str:
    ant_signal = ast["antecedent_signal"]
    ant = ant_signal if ast["antecedent_polarity"] == "high" else f"!{ant_signal}"
    cons_signal = ast["consequent_signal"]
    cons = {
        "high": cons_signal,
        "low": f"!{cons_signal}",
        "equal": f"({cons_signal} == {ant_signal})",
        "not_equal": f"({cons_signal} != {ant_signal})",
    }[ast["relation"]]
    event = f"posedge {clock}" if clock else f"{ant_signal} or {cons_signal}"
    disable = ""
    if reset:
        active = f"!{reset}" if reset.endswith(("_n", "_ni", "n")) else reset
        disable = f" disable iff ({active})"
    return f"assert property (@({event}){disable} ({ant}) {ast['implication']} ({cons}));"


def native_parse(sva: str, signals: list[str]) -> tuple[bool, list[str], str]:
    from pyslang.ast import Compilation
    from pyslang.syntax import SyntaxTree

    text = "module smoke_v2_native;\n" + "\n".join(f"logic {s};" for s in signals) + f"\nSMOKE_V2: {sva}\nendmodule\n"
    tree = SyntaxTree.fromText(text)
    compilation = Compilation()
    compilation.addSyntaxTree(tree)
    diagnostics = [str(item) for item in compilation.getAllDiagnostics()]
    return not diagnostics, diagnostics, text


def checker(ast: dict, tb_module: str, clock: str | None, reset: str | None, signals: list[str]) -> str:
    names = sorted(signals, key=len, reverse=True)
    pattern = r"\b(" + "|".join(map(re.escape, names)) + r")\b"
    qualify = lambda expression: re.sub(pattern, lambda m: f"{tb_module}.{m.group(1)}", expression)
    ant_signal = ast["antecedent_signal"]
    ant = ant_signal if ast["antecedent_polarity"] == "high" else f"!{ant_signal}"
    cons_signal = ast["consequent_signal"]
    cons = {
        "high": cons_signal,
        "low": f"!{cons_signal}",
        "equal": f"({cons_signal} == {ant_signal})",
        "not_equal": f"({cons_signal} != {ant_signal})",
    }[ast["relation"]]
    aq, cq = qualify(ant), qualify(cons)
    event = "*" if not clock else f"posedge {tb_module}.{clock}"
    reset_expr = "1'b0"
    if reset:
        qualified = f"{tb_module}.{reset}"
        reset_expr = f"!{qualified}" if reset.endswith(("_n", "_ni", "n")) else qualified
    fail = f"ant_d && !({cq})" if clock and ast["implication"] == "|=>" else f"({aq}) && !({cq})"
    return (
        "module smoke_v2_checker;\n"
        "integer antecedent_hits = 0;\n"
        "integer failure_hits = 0;\n"
        "reg ant_d = 0;\n"
        f"always @({event}) begin\n"
        f"  if ({reset_expr}) ant_d <= 0;\n"
        "  else begin\n"
        f"    if ({aq}) antecedent_hits = antecedent_hits + 1;\n"
        f"    if ({fail}) failure_hits = failure_hits + 1;\n"
        f"    ant_d <= ({aq});\n"
        "  end\n"
        "end\n"
        "endmodule\n"
    )


def run_compile(command: list[str], log_dir: Path, tag: str) -> dict:
    began = time.perf_counter()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        record = {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "timeout": False}
    except subprocess.TimeoutExpired as exc:
        record = {"command": command, "returncode": None, "stdout": exc.stdout or "", "stderr": exc.stderr or "", "timeout": True}
    record["wall_clock_seconds"] = time.perf_counter() - began
    dump(log_dir / f"{tag}_compile.json", record)
    return record


def main() -> None:
    if not shutil.which("iverilog"):
        raise SystemExit("ERROR: run inside WSL/Linux with iverilog on PATH")
    import pyslang
    iverilog_version = subprocess.run(["iverilog", "-V"], capture_output=True, text=True).stdout.splitlines()
    tool_versions = {
        "python": sys.version,
        "pyslang": getattr(pyslang, "__version__", "unknown"),
        "iverilog": iverilog_version[:2],
    }
    with (PILOT1 / "selected_train_parents.csv").open(encoding="utf-8-sig", newline="") as handle:
        parent_rows = {row["parent_bug_id"]: row for row in csv.DictReader(handle)}
    interfaces = {}
    for path in sorted((PILOT1 / "sequential_generation_v3_pilot30").rglob("evidence.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        interfaces.setdefault(value["parent_bug_id"], {"signals": value["signals"], "clock": value.get("clock"), "reset": value.get("reset")})

    source_manifest = SOURCE / "smoke_manifest.json"
    records = []
    for evidence_path in sorted((SOURCE / "generations").rglob("evidence.json")):
        source_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        method, parent, slot = source_evidence["method"], source_evidence["parent"], int(source_evidence["slot"])
        source_dir = evidence_path.parent
        dest = OUT / "records" / method / parent / f"slot_{slot:02d}"
        dest.mkdir(parents=True, exist_ok=True)
        ast = json.loads((source_dir / "ast.json").read_text(encoding="utf-8"))
        interface = interfaces[parent]
        signals, clock, reset = interface["signals"], interface["clock"], interface["reset"]
        schema_ok = tuple(ast) == KEYS and set(ast) == set(KEYS)
        used = {ast.get("antecedent_signal"), ast.get("consequent_signal")}
        signal_legal = used <= set(signals) and not used.intersection({clock, reset})
        sva = render(ast, clock, reset)
        (dest / "candidate.sva").write_text(sva + "\n", encoding="utf-8")
        native_ok, diagnostics, native_input = native_parse(sva, signals)
        (dest / "pyslang_input.sv").write_text(native_input, encoding="utf-8")
        dump(dest / "pyslang_diagnostics.json", diagnostics)

        metadata = parent_rows[parent]
        case = ROOT / metadata["dataset_root"] / metadata["case_id"]
        tb_path = case / "tb.v"
        tb_text = tb_path.read_text(encoding="utf-8")
        module_match = re.search(r"\bmodule\s+(\w+)", tb_text)
        if not module_match:
            raise RuntimeError(f"testbench module not found: {tb_path}")
        monitor = checker(ast, module_match.group(1), clock, reset, signals)
        monitor_path = dest / "checker.sv"
        monitor_path.write_text(monitor, encoding="utf-8")
        compile_runs = {}
        for rtl_name in ("correct.v", "buggy.v"):
            tag = rtl_name[:-2]
            executable = dest / f"{tag}.out"
            command = [
                "iverilog", "-g2012",
                "-I", str(case),
                "-I", str(ROOT / "external/common_cells/include"),
                "-o", str(executable),
                str(case / rtl_name), str(tb_path), str(monitor_path),
            ]
            compile_runs[tag] = run_compile(command, dest, tag)
        record = {
            "status": "complete",
            "method": method,
            "parent": parent,
            "slot": slot,
            "source_evidence_path": str(evidence_path.relative_to(ROOT)).replace("\\", "/"),
            "source_evidence_sha256": sha(evidence_path),
            "ast_sha256": sha(source_dir / "ast.json"),
            "schema_valid": schema_ok,
            "render_ok": True,
            "sva_sha256": sha(dest / "candidate.sva"),
            "signal_legal": signal_legal,
            "pyslang_ok": native_ok,
            "pyslang_diagnostics": diagnostics,
            "icarus_correct_compile_ok": compile_runs["correct"]["returncode"] == 0,
            "icarus_buggy_compile_ok": compile_runs["buggy"]["returncode"] == 0,
            "icarus_compile_ok": all(run["returncode"] == 0 for run in compile_runs.values()),
            "compile_timeout": any(run["timeout"] for run in compile_runs.values()),
        }
        dump(dest / "validation_evidence.json", record)
        records.append(record)
        print(method, parent, slot, record["signal_legal"], record["pyslang_ok"], record["icarus_compile_ok"], flush=True)

    dimensions = ("schema_valid", "render_ok", "signal_legal", "pyslang_ok", "icarus_compile_ok")
    totals = {key: sum(bool(row[key]) for row in records) for key in dimensions}
    groups = {}
    for row in records:
        key = f"{row['method']}::{row['parent']}"
        groups.setdefault(key, []).append(row)
    group_gate = {key: len(rows) == 8 and all(all(row[field] for field in dimensions) for row in rows) for key, rows in groups.items()}
    summary = {
        "status": "pass" if len(records) == 120 and all(value == 120 for value in totals.values()) and all(group_gate.values()) else "fail",
        "source_manifest_sha256": sha(source_manifest),
        "record_count": len(records),
        "totals": totals,
        "timeouts": sum(bool(row["compile_timeout"]) for row in records),
        "tool_versions": tool_versions,
        "group_8_of_8": group_gate,
        "gate_definition": "all five methods x three parents x eight one-shot ASTs pass schema, deterministic render, visible-signal, native pyslang, and correct+buggy Icarus monitor compilation",
    }
    dump(OUT / "validation_summary.json", summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
