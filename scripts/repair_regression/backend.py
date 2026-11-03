"""Isolated Icarus execution, reusing only the reviewed checker frontend."""
import re
import shlex
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
import contract_v3_checker as checker
from obligation_evidence_monitor import check_inputs
from .cases import metadata
from .contracts import digest, file_hash, read, write


def command(argv, folder, name, timeout):
    start = time.monotonic()
    try:
        p = subprocess.run(list(map(str, argv)), cwd=folder, capture_output=True, timeout=timeout)
        status, code, stdout, stderr = ("ok" if p.returncode == 0 else "error"), p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        status, code, stdout, stderr = "timeout", None, e.stdout or b"", e.stderr or b""
    except OSError as e:
        status, code, stdout, stderr = "error", None, b"", str(e).encode()
    (folder / (name + ".stdout")).write_bytes(stdout)
    (folder / (name + ".stderr")).write_bytes(stderr)
    result = dict(argv=list(map(str, argv)), cwd=str(folder), status=status, exit_code=code,
                  timeout=timeout, seconds=time.monotonic() - start)
    write(folder / (name + ".command.json"), result)
    return result


def preflight(c, out):
    folder = out / "tools"
    folder.mkdir(exist_ok=True)
    cfg = c["tool_config"]
    result = {"executables": {n: shutil.which(cfg.get(n, n)) for n in ["iverilog", "vvp", "jasper", "verilator", "ollama", "ssh"]},
              "remote": "No remote endpoint in CaseInput; legacy batch runner requires an explicit Jasper binary.",
              "runtime": "WSL/Linux" if str(out).startswith("/mnt/") else "local"}
    result["executable_hashes"] = {n: file_hash(p) for n, p in result["executables"].items() if p}
    for name, flag in [("iverilog", "-V"), ("vvp", "-V")]:
        result[name] = command([cfg[name], flag], folder, name, 10)
    try:
        import json
        with urllib.request.urlopen(cfg["model_url"] + "/api/tags", timeout=3) as r:
            tags = json.load(r)
        result["model_service"] = dict(status="reachable", models=[m.get("name") for m in tags.get("models", [])],
                                       generation="not_used: explicitly selected offline template provider")
    except Exception as e:
        result["model_service"] = dict(status="unavailable", error=str(e), generation="offline_template")
    result["native_sva"] = "not_executed; Icarus procedural monitor only"
    result["formal"] = "not_executed"
    write(folder / "availability.json", result)
    return result


def parse_stdout(text):
    trace, checks = [], {}
    for raw in text.splitlines():
        if raw.startswith("TRACE "):
            parts = raw.split()
            row = {"cycle": int(parts[1])}
            for item in parts[2:]:
                n, v = item.split("=")
                row[n] = int(v) if re.fullmatch(r"-?\d+", v) else None
            trace.append(row)
        elif raw.startswith("CHECK "):
            _, j, t, a, f = raw.split()
            checks.setdefault(j, []).append(dict(cycle=int(t), trigger=int(a) if a.isdigit() else None,
                                                 fail=int(f) if f.isdigit() else None))
    return trace, checks


def validate_assertions(c, aset):
    d = metadata(c)
    for a in aset["assertions"]:
        if a["content_hash"] != digest({k: a[k] for k in ("antecedent", "consequent", "delay")}):
            raise ValueError("Assertion hash mismatch")
        checker.normalize(a, d, a["authorized_history_depth"])
        # Reset/disable and environmental assumptions cannot be supplied by candidates.
        if a["tool_support"] != "restricted_monitor":
            raise ValueError("unsupported tool capability")


class Backend:
    def __init__(self, c, out):
        self.case, self.out = c, Path(out)

    def execute(self, rows, variant, aset=None, namespace="runs", tb_transform=None):
        c, d = self.case, metadata(self.case)
        assertions = aset["assertions"] if aset else []
        key = digest([digest(c), rows, variant, assertions, namespace])
        folder = self.out / namespace / key
        if (folder / "result.json").exists():
            result = read(folder / "result.json")
            # Cache only complete results whose artifacts have not changed.
            if all((folder / p).exists() and file_hash(folder / p) == h for p, h in result["artifact_hashes"].items()):
                return result
            raise ValueError("Cached artifacts changed: " + str(folder))
        folder.mkdir(parents=True, exist_ok=True)
        write(folder / "stimulus.json", rows)
        write(folder / "assertion_set.json", aset)
        result = dict(run=str(folder), status="unknown", variant=variant, trace=[], checks={}, reason=None,
                      config_hash=digest(c), input_hash=digest(rows), commands=[], artifact_hashes={})
        def finish(status, reason=None):
            result.update(status=status, reason=reason)
            write(folder / "trace.json", result["trace"])
            write(folder / "checks.json", result["checks"])
            result["artifact_hashes"] = {p.name: file_hash(p) for p in folder.iterdir() if p.is_file() and p.name != "result.json"}
            write(folder / "result.json", result)
            return result
        errors = check_inputs(d, rows)
        if not rows or rows[0].get(d["rst"]) != 0 or errors:
            return finish("unknown", "invalid_input_or_initialization: " + str(errors))
        if c["tool_config"]["backend"] != "iverilog":
            return finish("unsupported", "Jasper is a separately reported formal capability; no implicit backend substitution")
        try:
            if aset:
                validate_assertions(c, aset)
            text = checker.tb_text(d, rows, assertions)
        except (AssertionError, ValueError, KeyError, TypeError) as e:
            return finish("unsupported", str(e))
        # Fix the documented legacy history reset limitation without monkey-patching globals.
        before = f'always @(posedge {d["clk"]}) begin\np1_'
        after = f'always @(posedge {d["clk"]} or negedge {d["rst"]}) begin\np1_'
        if text.count(before) != 1:
            return finish("error", "Legacy TB structure changed")
        text = text.replace(before, after, 1)
        if tb_transform:
            text = tb_transform(text)
        (folder / "checker_tb.sv").write_text(text, encoding="utf-8")
        cfg, rtl = c["tool_config"], c["rtl"][variant]
        args = [cfg["iverilog"], "-g2012", "-s", "tb", "-o", "sim.out"]
        for p in rtl["include_dirs"]:
            args += ["-I", p]
        for p in rtl["defines"]:
            args += ["-D", p]
        args += rtl["sources"] + ["checker_tb.sv"]
        (folder / "reproduce.sh").write_text("#!/bin/sh\nset -eu\ncd " + shlex.quote(str(folder)) + "\n" +
            shlex.join(args) + "\n" + shlex.join([cfg["vvp"], "sim.out"]) + "\n", encoding="utf-8")
        build = command(args, folder, "compile", cfg["timeout_seconds"])
        result["commands"].append(build)
        if build["status"] != "ok":
            return finish(build["status"], "RTL/monitor compilation failed")
        sim = command([cfg["vvp"], "sim.out"], folder, "simulate", cfg["timeout_seconds"])
        result["commands"].append(sim)
        if sim["status"] != "ok":
            return finish(sim["status"], "Simulation did not complete")
        trace, checks = parse_stdout((folder / "simulate.stdout").read_text(errors="replace"))
        result.update(trace=trace, checks=checks)
        # Timing is checked before any transaction association. No waveform shifts.
        if len(trace) != len(rows) or [r["cycle"] for r in trace] != list(range(len(rows))):
            return finish("unknown", "sampling_incomplete_or_extra_response")
        for r, inp in zip(trace, rows):
            if any(r.get(n) != inp[n] for n in [d["rst"], *d["inputs"]]):
                return finish("unknown", "sampled_input_mismatch")
            if r[d["rst"]] and any(r.get(n) is None for n in d["outputs"]):
                return finish("unknown", "four_state_output")
        active = [r["cycle"] for r in trace if r[d["rst"]]]
        for j, a in enumerate(assertions):
            cc = checks.get(str(j), [])
            if [x["cycle"] for x in cc] != active or any(x["fail"] is None or x["trigger"] is None for x in cc):
                return finish("unknown", "checker_missing_or_four_state")
            for x in cc:
                if x["trigger"] and x["cycle"] + a["delay"] >= len(rows):
                    if all(r[d["rst"]] for r in rows[x["cycle"]:]):
                        return finish("unknown", "pending_response_at_end")
        return finish("ok")
