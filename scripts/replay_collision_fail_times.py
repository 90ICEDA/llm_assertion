#!/usr/bin/env python3
"""Instrument existing probe checkers and replay selected count-difference runs.

Usage in WSL: python3 scripts/replay_collision_fail_times.py [--limit N]
Does not modify original RTL, stimulus, checker, binary, or result.json files.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "deliverables/feedback_collision_reaudit_20261002"


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def rel(p):
    return p.relative_to(ROOT).as_posix()


def instrument(text, deferred=False):
    fail = "fail_hits=fail_hits+1;"
    ant = "ant_hits=ant_hits+1;"
    if text.count(fail) != 1 or text.count(ant) != 1:
        raise ValueError("unexpected checker metric template")
    if deferred:
        text = text.replace('module v3_probe_checker;', 'module v3_probe_checker; time fail_t[0:9999], ant_t[0:9999]; integer audit_i;')
        text = text.replace(fail, 'begin fail_hits=fail_hits+1; fail_t[fail_hits]=$time; end')
        text = text.replace(ant, 'begin ant_hits=ant_hits+1; ant_t[ant_hits]=$time; end')
        text = text.replace('endmodule', 'final begin for(audit_i=1;audit_i<=ant_hits;audit_i=audit_i+1) $display("AUDIT_ANT t=%0t", ant_t[audit_i]); for(audit_i=1;audit_i<=fail_hits;audit_i=audit_i+1) $display("AUDIT_FAIL t=%0t", fail_t[audit_i]); end endmodule')
    else:
        text = text.replace(fail, 'begin fail_hits=fail_hits+1; $display("AUDIT_FAIL t=%0t", $time); end')
        text = text.replace(ant, 'begin ant_hits=ant_hits+1; $display("AUDIT_ANT t=%0t", $time); end')
    return "`timescale 1ns/1ps\n" + text


def one(path, deferred=False):
    d = load(path)
    original_checker = ROOT / d["checker_path"]
    parent = d["candidate_id"].split("__v3_slot_")[0]
    probe = d["probe_id"].rsplit("__", 1)[-1]
    slot = d["candidate_id"].rsplit("_", 1)[-1]
    out = AUDIT / ("time_replays_deferred" if deferred else "time_replays") / parent / probe / f"slot_{slot}"
    out.mkdir(parents=True, exist_ok=True)
    checker = out / "checker_timed.sv"
    checker.write_text(instrument(original_checker.read_text(encoding="utf-8"), deferred), encoding="utf-8")
    record = {"source_result": rel(path), "source_checker": rel(original_checker), "timed_checker": rel(checker), "runs": {}}
    for design in ("correct", "buggy"):
        source = d["rtl"][design]
        cmd = list(source["compile_command"])
        binary = out / f"{design}.out"
        cmd[cmd.index("-o") + 1] = str(binary)
        cmd[-1] = str(checker)
        compiled = subprocess.run(cmd, cwd=out, text=True, capture_output=True, timeout=60)
        simcmd = ["vvp", str(binary)]
        sim = subprocess.run(simcmd, cwd=out, text=True, capture_output=True, timeout=60) if compiled.returncode == 0 else None
        stdout = sim.stdout if sim else ""
        (out / f"{design}.compile.stdout").write_text(compiled.stdout, encoding="utf-8")
        (out / f"{design}.compile.stderr").write_text(compiled.stderr, encoding="utf-8")
        (out / f"{design}.sim.stdout").write_text(stdout, encoding="utf-8")
        (out / f"{design}.sim.stderr").write_text(sim.stderr if sim else "", encoding="utf-8")
        ants = [int(x) for x in re.findall(r"AUDIT_ANT t=(\d+)", stdout)]
        fails = [int(x) for x in re.findall(r"AUDIT_FAIL t=(\d+)", stdout)]
        record["runs"][design] = {
            "compile_command": cmd, "simulation_command": simcmd,
            "compile_exit": compiled.returncode, "simulation_exit": sim.returncode if sim else None,
            "antecedent_times_ps": ants, "failure_times_ps": fails,
            "original_antecedent_hits": source["antecedent_hits"],
            "original_fail_hits": source["fail_hits"],
            "metrics_match": len(ants) == source["antecedent_hits"] and len(fails) == source["fail_hits"] if sim else False,
            "stdout_path": rel(out / f"{design}.sim.stdout"),
            "stderr_path": rel(out / f"{design}.sim.stderr"),
        }
    record["replay_path"] = rel(out / "replay.json")
    (out / "replay.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--deferred", action="store_true")
    parser.add_argument("--mismatches", action="store_true")
    args = parser.parse_args()
    rows = [json.loads(s) for s in (AUDIT / "pairs.jsonl").read_text(encoding="utf-8").splitlines()]
    unique = sorted({x[key] for r in rows if r["count_difference"] for x in r["count_difference_probes"] for key in ("a_result", "b_result")})
    if args.mismatches:
        old = load(AUDIT / "time_replay_index.json")
        mismatch = {r["source_result"] for r in old if not r["metrics_match"]}
        unique = [x for x in unique if x in mismatch]
    if args.limit is not None:
        unique = unique[:args.limit]
    records = []
    failures = []
    for n, source in enumerate(unique, 1):
        try:
            record = one(ROOT / source, args.deferred)
            records.append({"source_result": source, "replay": record["replay_path"],
                            "metrics_match": all(v["metrics_match"] for v in record["runs"].values())})
        except Exception as exc:
            failures.append({"source_result": source, "error": str(exc)})
        if n % 100 == 0:
            print(f"processed {n}/{len(unique)}", flush=True)
    summary = {"selected_runs": len(unique), "completed": len(records), "metric_matches": sum(x["metrics_match"] for x in records), "failures": len(failures)}
    prefix = "deferred_time_replay" if args.deferred else "time_replay"
    (AUDIT / f"{prefix}_index.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    (AUDIT / f"{prefix}_failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    (AUDIT / f"{prefix}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
