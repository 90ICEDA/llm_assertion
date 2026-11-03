#!/usr/bin/env python3
"""Trace original compiled collision probes using the read-only VPI monitor.

Run inside WSL after building fail_time_vpi.vpi with iverilog-vpi. All original
RTL, stimuli, checker sources, binaries and result JSON files stay untouched.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "deliverables/feedback_collision_reaudit_20261002"
MODULE = AUDIT / "fail_time_vpi.vpi"


def rel(p):
    return p.relative_to(ROOT).as_posix()


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    if not MODULE.exists():
        cmd = ["iverilog-vpi", "-o", str(MODULE), str(ROOT / "scripts/fail_time_vpi.c")]
        built = subprocess.run(cmd, cwd=AUDIT, text=True, capture_output=True, timeout=60)
        (AUDIT / "vpi_build.stdout").write_text(built.stdout, encoding="utf-8")
        (AUDIT / "vpi_build.stderr").write_text(built.stderr, encoding="utf-8")
        if built.returncode:
            raise RuntimeError(f"VPI build failed: {built.returncode}")
    pairs = [json.loads(s) for s in (AUDIT / "pairs.jsonl").read_text(encoding="utf-8").splitlines()]
    unique = sorted({x[key] for p in pairs if p["count_difference"] for x in p["count_difference_probes"] for key in ("a_result", "b_result")})
    records, failures = [], []
    for i, source in enumerate(unique, 1):
        try:
            d = load(ROOT / source)
            parent = d["candidate_id"].split("__v3_slot_")[0]
            probe = d["probe_id"].rsplit("__", 1)[-1]
            slot = d["candidate_id"].rsplit("_", 1)[-1]
            out = AUDIT / "vpi_replays" / parent / probe / f"slot_{slot}"
            out.mkdir(parents=True, exist_ok=True)
            record = {"source_result": source, "vpi_module": rel(MODULE), "runs": {}}
            for design in ("correct", "buggy"):
                original = d["rtl"][design]
                binary = original["simulation_command"][-1]
                cmd = ["vvp", "-M", str(AUDIT), "-m", "fail_time_vpi", binary]
                run = subprocess.run(cmd, cwd=out, text=True, capture_output=True, timeout=60)
                stdout_path = out / f"{design}.stdout"
                stderr_path = out / f"{design}.stderr"
                stdout_path.write_text(run.stdout, encoding="utf-8")
                stderr_path.write_text(run.stderr, encoding="utf-8")
                ants = [(int(t), int(v)) for t,v in re.findall(r"AUDIT_VPI_ANT t_ticks=(\d+) value=(\d+)", run.stdout)]
                fails = [(int(t), int(v)) for t,v in re.findall(r"AUDIT_VPI_FAIL t_ticks=(\d+) value=(\d+)", run.stdout)]
                ant_times = [t for t,v in ants if v > 0]
                fail_times = [t for t,v in fails if v > 0]
                record["runs"][design] = {"command": cmd, "exit_code": run.returncode,
                    "antecedent_times_ps": ant_times, "failure_times_ps": fail_times,
                    "original_antecedent_hits": original["antecedent_hits"],
                    "original_fail_hits": original["fail_hits"],
                    "metrics_match": run.returncode == 0 and len(ant_times) == original["antecedent_hits"] and len(fail_times) == original["fail_hits"],
                    "stdout_path": rel(stdout_path), "stderr_path": rel(stderr_path)}
            replay_path = out / "replay.json"
            record["replay_path"] = rel(replay_path)
            replay_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            records.append({"source_result": source, "replay": rel(replay_path),
                            "metrics_match": all(v["metrics_match"] for v in record["runs"].values())})
        except Exception as exc:
            failures.append({"source_result": source, "error": str(exc)})
        if i % 100 == 0:
            print(f"processed {i}/{len(unique)}", flush=True)
    summary = {"selected_runs": len(unique), "completed": len(records),
               "metric_matches": sum(x["metrics_match"] for x in records), "failures": len(failures)}
    (AUDIT / "vpi_time_replay_index.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    (AUDIT / "vpi_time_replay_failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    (AUDIT / "vpi_time_replay_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
