from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/behavioral_preference_pilot_v1"
GEN = BASE / "sequential_generation_v3_pilot30"
OUT = BASE / "behavioral_probes_v3"
SEED = 20260815
POOL_TARGET = 64
BUDGET = 32


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")


def module_name(text: str) -> str:
    match = re.search(r"\bmodule\s+(\w+)", text)
    if not match:
        raise ValueError("testbench has no module declaration")
    return match.group(1)


def source_path(arg: str) -> Path:
    if arg.startswith("/mnt/d/"):
        return Path(arg) if os.name != "nt" else Path("D:/" + arg[len("/mnt/d/"):])
    if re.match(r"^[Dd]:[/\\]", arg) and os.name != "nt":
        return Path("/mnt/d/" + arg[3:].replace("\\", "/"))
    return Path(arg)


def locate_sources(evidence: dict) -> tuple[Path, Path, Path]:
    command = evidence["runs"]["correct"]["command"]
    verilog = [source_path(x) for x in command if str(x).endswith((".v", ".sv"))]
    checker = source_path(next(x for x in command if str(x).endswith("checker.sv")))
    tb = next(x for x in verilog if x.name in {"tb.v", "compat_tb.v"})
    rtl = next(x for x in verilog if x != tb and x != checker)
    buggy_cmd = evidence["runs"]["buggy"]["command"]
    buggy_verilog = [source_path(x) for x in buggy_cmd if str(x).endswith((".v", ".sv"))]
    buggy = next(x for x in buggy_verilog if x.name not in {"tb.v", "compat_tb.v", "checker.sv"})
    return rtl.resolve(), buggy.resolve(), tb.resolve()


def tb_sources(primary: Path) -> list[tuple[str, Path]]:
    case = primary.parent
    found = [("target", primary)]
    for label, name in (("holdout", "tb_holdout.v"), ("decoy", "tb_decoy.v")):
        path = case / name
        if path.exists():
            found.append((label, path))
    # Compatibility TBs live in evidence directories, while holdout/decoy remain
    # beside the original RTL. The target TB is still retained as a pool member.
    return found


def materialize_tb(path: Path) -> str:
    """Expand local TB include wrappers so transforms reach actual stimulus."""
    text = path.read_text(encoding="utf-8")
    include = re.compile(r'`include\s+"([^"]+)"')
    for _ in range(4):
        changed = False
        def expand(match: re.Match) -> str:
            nonlocal changed
            target = path.parent / match.group(1)
            if not target.exists():
                return match.group(0)
            changed = True
            return target.read_text(encoding="utf-8")
        text = include.sub(expand, text)
        if not changed:
            break
    return text


def clock_reset(evidence: dict) -> tuple[str | None, str | None]:
    return evidence.get("clock"), evidence.get("reset")


def transform_tb(text: str, *, probe_no: int, label: str, clock: str | None,
                 reset: str | None, semantic: list[str]) -> tuple[str, dict]:
    """Create deterministic, source-level legal input variations.

    The transform changes only testbench stimulus: vector data values, request
    spacing, ready/backpressure values, and reset release/pulse placement. It
    never edits DUT or checker behavior. Compile success is required later.
    """
    rng = random.Random(SEED ^ (probe_no * 0x9E3779B1) ^ int(hashlib.sha256(label.encode()).hexdigest()[:8], 16))
    family = probe_no % 5
    changes: list[dict] = []
    out = text

    # Make dump paths collision-free without changing behavior.
    out = re.sub(r'\$dumpfile\s*\(\s*"[^"]*"\s*\)', f'$dumpfile("probe_{probe_no:03d}.vcd")', out)

    # Data/address renaming analogue: consistently permute non-control literal
    # values assigned to visible vector-like inputs. Width is preserved.
    control_words = ("clk", "rst", "reset", "valid", "ready", "push", "pop", "enable", "flush", "clear")
    data_names = [s for s in semantic if not any(w in s.lower() for w in control_words)]
    if family in (0, 4) and data_names:
        chosen = data_names[probe_no % len(data_names)]
        pat = re.compile(rf"\b({re.escape(chosen)})\s*=\s*(\d+)'([bBdDhH])([0-9a-fA-F_xXzZ]+)")
        def remap(match: re.Match) -> str:
            width = int(match.group(2)); base = match.group(3).lower(); raw = match.group(4)
            if any(c in raw.lower() for c in "xz_"):
                return match.group(0)
            radix = {"b": 2, "d": 10, "h": 16}[base]
            value = int(raw, radix); mask = (1 << min(width, 31)) - 1
            new = (value ^ (1 + rng.randrange(max(1, mask)))) & mask
            rendered = {"b": format(new, "b"), "d": str(new), "h": format(new, "x")}[base]
            changes.append({"family": "data_address_value", "signal": chosen, "old": match.group(0), "new_value": new})
            return f"{match.group(1)} = {width}'{match.group(3)}{rendered}"
        out = pat.sub(remap, out)

    # Request interval / stall-backpressure: insert genuine extra clock gaps.
    if clock and family in (1, 2):
        gap = 1 + (probe_no % 3)
        marker = re.compile(rf"(@\s*\(\s*(?:pos|neg)edge\s+{re.escape(clock)}\s*\)\s*;)")
        matches = list(marker.finditer(out))
        if matches:
            selected = matches[probe_no % len(matches)]
            insertion = f" repeat ({gap}) @(posedge {clock});"
            out = out[:selected.end()] + insertion + out[selected.end():]
            changes.append({"family": "request_spacing" if family == 1 else "stall_backpressure", "cycles": gap})

    # Reset translation: lengthen initial reset or add a late legal reset pulse.
    if reset and clock and family == 3:
        repeat_pat = re.compile(r"repeat\s*\(\s*(\d+)\s*\)\s*@\s*\(\s*posedge")
        match = repeat_pat.search(out)
        if match:
            old = int(match.group(1)); new = old + 1 + probe_no % 2
            out = out[:match.start(1)] + str(new) + out[match.end(1):]
            changes.append({"family": "reset_translation", "initial_cycles_old": old, "initial_cycles_new": new})
        else:
            active = "0" if reset.endswith(("_n", "_ni", "n")) else "1"
            inactive = "1" if active == "0" else "0"
            pulse = f"{reset}=1'b{active}; repeat (2) @(posedge {clock}); {reset}=1'b{inactive}; @(posedge {clock}); "
            out, count = re.subn(r"\$finish\s*;", pulse + "$finish;", out, count=1)
            if count:
                changes.append({"family": "reset_translation", "late_pulse_cycles": 2})

    # Every query receives a distinct observation horizon. This is behavioral,
    # not a comment/tag: sequential assertions observe 1..64 additional clock
    # samples. It also keeps delay-only one-line testbenches (case438/case441)
    # from collapsing to fewer than 32 unique executable stimuli.
    if clock:
        gap = probe_no + 1
        out, count = re.subn(r"\$finish\s*;", f"repeat ({gap}) @(posedge {clock}); $finish;", out, count=1)
        if count:
            changes.append({"family": "observation_window_extension", "cycles": gap})
    else:
        delay = probe_no + 1
        out, count = re.subn(r"\$finish\s*;", f"#{delay}; $finish;", out, count=1)
        if count:
            changes.append({"family": "combinational_observation_window_extension", "time_units": delay})

    return out, {"source_label": label, "probe_number": probe_no, "transformations": changes}


def qualify(expr: str, tbmod: str, signals: list[str]) -> str:
    pattern = r"\b(" + "|".join(map(re.escape, sorted(signals, key=len, reverse=True))) + r")\b"
    return re.sub(pattern, lambda m: f"{tbmod}.{m.group(1)}", expr)


def checker_text(evidence: dict, tbmod: str) -> str:
    ast = evidence["ast"]
    signal = ast["antecedent_signal"]
    ant = signal if ast["antecedent_polarity"] == "high" else "!" + signal
    if evidence["slot"] == 8:
        ant = f"({signal} && !{signal})"
    cons_signal = ast["consequent_signal"]
    cons = {
        "high": cons_signal,
        "low": "!" + cons_signal,
        "equal": f"({cons_signal} == {signal})",
        "not_equal": f"({cons_signal} != {signal})",
    }[ast["relation"]]
    aq = qualify(ant, tbmod, evidence["signals"])
    cq = qualify(cons, tbmod, evidence["signals"])
    clk, rst = clock_reset(evidence)
    event = "*" if not clk else "posedge " + tbmod + "." + clk
    reset = "1'b0" if not rst else (("!" if rst.endswith(("_n", "_ni", "n")) else "") + tbmod + "." + rst)
    fail = f"ant_d && !({cq})" if clk and ast["implication"] == "|=>" else f"({aq}) && !({cq})"
    return (f'module v3_probe_checker; integer ant_hits=0,fail_hits=0; reg ant_d=0; '
            f'always @({event}) begin if({reset}) ant_d<=0; else begin if({aq}) ant_hits=ant_hits+1; '
            f'if({fail}) fail_hits=fail_hits+1; ant_d<=({aq}); end end '
            f'final $display("V3_PROBE_METRIC ant_hits=%0d fail_hits=%0d",ant_hits,fail_hits); endmodule\n')


def execute(cmd: list[str], timeout: int = 120) -> dict:
    started = time.perf_counter()
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"returncode": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr,
                "timeout": False, "wall_clock_seconds": time.perf_counter() - started}
    except subprocess.TimeoutExpired as exc:
        return {"returncode": None, "stdout": exc.stdout or "", "stderr": exc.stderr or "",
                "timeout": True, "wall_clock_seconds": time.perf_counter() - started}


def run_candidate(parent_dir: Path, probe: dict, evidence: dict, correct: Path, buggy: Path) -> dict:
    candidate_id = f'{evidence["parent_bug_id"]}__v3_slot_{evidence["slot"]:02d}'
    run_dir = parent_dir / "runs" / probe["probe_id"] / candidate_id
    run_dir.mkdir(parents=True, exist_ok=True)
    tb_path = ROOT / probe["stimulus_path"]
    checker = run_dir / "checker.sv"
    checker.write_text(checker_text(evidence, module_name(tb_path.read_text(encoding="utf-8"))), encoding="utf-8")
    result = {"candidate_id": candidate_id, "probe_id": probe["probe_id"], "checker_path": rel(checker),
              "checker_sha256": sha(checker), "rtl": {}}
    for kind, rtl in (("correct", correct), ("buggy", buggy)):
        exe = run_dir / f"{kind}.out"
        cmd = ["iverilog", "-g2012", "-I", str(rtl.parent), "-I", str(ROOT / "external/common_cells/include"),
               "-o", str(exe), str(rtl), str(tb_path), str(checker)]
        compile_result = execute(cmd, timeout=60)
        sim_cmd = ["vvp", str(exe)]
        sim_result = execute(sim_cmd, timeout=10) if compile_result["returncode"] == 0 else None
        merged = "" if sim_result is None else sim_result["stdout"] + sim_result["stderr"]
        match = re.search(r"V3_PROBE_METRIC ant_hits=(\d+) fail_hits=(\d+)", merged)
        result["rtl"][kind] = {"rtl_path": rel(rtl), "rtl_sha256": sha(rtl), "compile_command": cmd,
                               "compile": compile_result, "simulation_command": sim_cmd,
                               "simulation": sim_result, "antecedent_hits": int(match.group(1)) if match else 0,
                               "fail_hits": int(match.group(2)) if match else 0}
    cr, br = result["rtl"]["correct"], result["rtl"]["buggy"]
    result["executable"] = all(x["compile"]["returncode"] == 0 and x["simulation"] and x["simulation"]["returncode"] == 0 for x in (cr, br))
    result["fp"] = result["executable"] and cr["fail_hits"] > 0
    # A true-positive probe must distinguish buggy from correct; this prevents
    # an always-failing assertion from receiving TP credit.
    result["tp"] = result["executable"] and br["fail_hits"] > 0 and cr["fail_hits"] == 0
    result["distinguishing"] = result["executable"] and cr["fail_hits"] != br["fail_hits"]
    dump(run_dir / "result.json", result)
    return result


def preflight_probe(parent_dir: Path, probe: dict, correct: Path, buggy: Path) -> dict:
    """Reject DUT/TB hangs once, before repeating the query for 8 checkers."""
    run_dir = parent_dir / "preflight" / probe["probe_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    tb_path = ROOT / probe["stimulus_path"]
    result = {"probe_id": probe["probe_id"], "rtl": {}}
    for kind, rtl in (("correct", correct), ("buggy", buggy)):
        exe = run_dir / f"{kind}.out"
        cmd = ["iverilog", "-g2012", "-I", str(rtl.parent), "-I", str(ROOT / "external/common_cells/include"),
               "-o", str(exe), str(rtl), str(tb_path)]
        compiled = execute(cmd, timeout=60)
        sim_cmd = ["vvp", str(exe)]
        simulated = execute(sim_cmd, timeout=10) if compiled["returncode"] == 0 else None
        result["rtl"][kind] = {"rtl_path": rel(rtl), "rtl_sha256": sha(rtl), "compile_command": cmd,
                               "compile": compiled, "simulation_command": sim_cmd, "simulation": simulated}
    result["executable"] = all(x["compile"]["returncode"] == 0 and x["simulation"]
                               and x["simulation"]["returncode"] == 0 and not x["simulation"]["timeout"]
                               for x in result["rtl"].values())
    dump(run_dir / "result.json", result)
    return result


def greedy_disagreement(probes: list[str], outcomes: dict[str, dict[str, tuple[bool, bool]]], candidates: list[str]) -> list[str]:
    selected: list[str] = []
    signatures = {c: tuple() for c in candidates}
    remaining = set(probes)
    while remaining and len(selected) < BUDGET:
        def score(probe_id: str):
            next_sigs = {c: signatures[c] + outcomes[probe_id][c] for c in candidates}
            groups = defaultdict(int)
            for value in next_sigs.values():
                groups[value] += 1
            separated_pairs = sum(a * b for i, a in enumerate(groups.values()) for b in list(groups.values())[i + 1:])
            distinct = len(groups)
            return separated_pairs, distinct, probe_id
        chosen = max(remaining, key=score)
        selected.append(chosen)
        for candidate in candidates:
            signatures[candidate] += outcomes[chosen][candidate]
        remaining.remove(chosen)
    return selected


def run_parent(parent_id: str, evidences: list[dict]) -> dict:
    started = time.perf_counter()
    parent_dir = OUT / parent_id
    correct, buggy, primary_tb = locate_sources(evidences[0])
    sources = tb_sources(primary_tb)
    semantic = [x for x in evidences[0]["signals"] if x not in {evidences[0].get("clock"), evidences[0].get("reset")}]
    pool = []
    for number in range(POOL_TARGET):
        label, path = sources[number % len(sources)]
        text = materialize_tb(path)
        transformed, metadata = transform_tb(text, probe_no=number, label=label,
                                             clock=evidences[0].get("clock"), reset=evidences[0].get("reset"),
                                             semantic=semantic)
        probe_id = f"{parent_id}__probe_{number:03d}"
        stimulus = parent_dir / "stimuli" / f"{probe_id}.v"
        stimulus.parent.mkdir(parents=True, exist_ok=True)
        stimulus.write_text(transformed, encoding="utf-8")
        pool.append({"probe_id": probe_id, "seed": SEED, "source_tb_path": rel(path),
                     "source_tb_sha256": sha(path), "stimulus_path": rel(stimulus),
                     "stimulus_sha256": sha(stimulus), **metadata})
    if len({x["stimulus_sha256"] for x in pool}) < BUDGET:
        raise RuntimeError(f"{parent_id}: fewer than {BUDGET} unique generated stimuli")

    preflights = [preflight_probe(parent_dir, probe, correct, buggy) for probe in pool]
    eligible_pool = [probe for probe in pool if next(x for x in preflights if x["probe_id"] == probe["probe_id"])["executable"]]
    if len(eligible_pool) < BUDGET:
        raise RuntimeError(f"{parent_id}: only {len(eligible_pool)} candidate-independent executable probes")
    runs = []
    for probe in eligible_pool:
        for evidence in sorted(evidences, key=lambda x: x["slot"]):
            runs.append(run_candidate(parent_dir, probe, evidence, correct, buggy))
    executable_probes = [p["probe_id"] for p in eligible_pool if all(r["executable"] for r in runs if r["probe_id"] == p["probe_id"])]
    if len(executable_probes) < BUDGET:
        raise RuntimeError(f"{parent_id}: only {len(executable_probes)} fully executable probes")
    candidates = sorted({r["candidate_id"] for r in runs})
    outcomes = {p: {c: (next(r for r in runs if r["probe_id"] == p and r["candidate_id"] == c)["fp"],
                         next(r for r in runs if r["probe_id"] == p and r["candidate_id"] == c)["tp"])
                    for c in candidates} for p in executable_probes}
    rng = random.Random(SEED ^ int(hashlib.sha256(parent_id.encode()).hexdigest()[:8], 16))
    random_selected = sorted(rng.sample(executable_probes, BUDGET))
    guided_selected = greedy_disagreement(executable_probes, outcomes, candidates)
    policies = {"random_legal": random_selected, "disagreement_guided": guided_selected}
    candidate_sets = []
    for policy, selected in policies.items():
        for candidate in candidates:
            selected_runs = [r for r in runs if r["candidate_id"] == candidate and r["probe_id"] in selected]
            candidate_sets.append({"parent_bug_id": parent_id, "candidate_id": candidate, "probe_policy": policy,
                                   "query_budget": BUDGET, "selected_probe_ids": selected,
                                   "fp_probe_ids": sorted(r["probe_id"] for r in selected_runs if r["fp"]),
                                   "tp_mutant_ids": sorted(r["probe_id"] + "@" + sha(buggy)[:16] for r in selected_runs if r["tp"]),
                                   "antecedent_hit_probe_ids": sorted(r["probe_id"] for r in selected_runs if r["rtl"]["buggy"]["antecedent_hits"] > 0),
                                   "distinguishing_probe_ids": sorted(r["probe_id"] for r in selected_runs if r["distinguishing"])})
    result = {"parent_bug_id": parent_id, "pool_size": len(pool), "unique_stimuli": len({p["stimulus_sha256"] for p in pool}),
              "preflight_executable_pool_size": len(eligible_pool),
              "preflight_timeout_probe_ids": sorted(x["probe_id"] for x in preflights if any(
                  r.get("simulation") and r["simulation"].get("timeout") for r in x["rtl"].values())),
              "fully_executable_pool_size": len(executable_probes), "query_budget_per_policy": BUDGET,
              "policies": policies, "candidate_sets": candidate_sets,
              "correct_rtl_path": rel(correct), "correct_rtl_sha256": sha(correct),
              "buggy_rtl_path": rel(buggy), "buggy_rtl_sha256": sha(buggy),
              "mutation_diff_path": rel(primary_tb.parent / "mutation.diff") if (primary_tb.parent / "mutation.diff").exists() else None,
              "mutation_diff_sha256": sha(primary_tb.parent / "mutation.diff") if (primary_tb.parent / "mutation.diff").exists() else None,
              "wall_clock_seconds": time.perf_counter() - started}
    dump(parent_dir / "probe_pool.json", {"parent_bug_id": parent_id, "probes": pool})
    dump(parent_dir / "parent_result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", action="append", help="Run only the named parent (repeatable).")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    gate = json.loads((GEN / "gate_result.json").read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for evidence in gate["evidence"]:
        grouped[evidence["parent_bug_id"]].append(evidence)
    requested = args.parent or sorted(grouped)
    results_by_parent = {}
    pending = []
    for parent in requested:
        saved = OUT / parent / "parent_result.json"
        if args.resume and saved.exists():
            prior = json.loads(saved.read_text(encoding="utf-8"))
            valid = (prior.get("pool_size") == POOL_TARGET and prior.get("unique_stimuli") == POOL_TARGET
                     and prior.get("fully_executable_pool_size", 0) >= BUDGET
                     and all(len(v) == BUDGET for v in prior.get("policies", {}).values()))
            if valid:
                results_by_parent[parent] = prior
                continue
        pending.append(parent)
    if args.jobs <= 1:
        for parent in pending:
            results_by_parent[parent] = run_parent(parent, grouped[parent])
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(run_parent, parent, grouped[parent]): parent for parent in pending}
            for future in as_completed(futures):
                parent = futures[future]
                results_by_parent[parent] = future.result()
                print(json.dumps({"completed_parent": parent, "completed": len(results_by_parent),
                                  "total": len(requested)}), flush=True)
    results = [results_by_parent[parent] for parent in requested]
    all_sets = [row for result in results for row in result["candidate_sets"]]
    generation_by_candidate = {}
    for parent, items in grouped.items():
        for evidence in items:
            candidate_id = f'{parent}__v3_slot_{evidence["slot"]:02d}'
            evidence_path = ROOT / Path(evidence["response_path"]).parent / "evidence.json"
            prompt_path = ROOT / Path(evidence["request_path"]).parent / "prompt.txt"
            response_path = ROOT / evidence["response_path"]
            sva_path = ROOT / Path(evidence["response_path"]).parent / "candidate.sva"
            generation_by_candidate[candidate_id] = {
                "generation_evidence_path": rel(evidence_path), "generation_evidence_sha256": sha(evidence_path),
                "prompt_path": rel(prompt_path), "prompt_sha256": sha(prompt_path),
                "raw_response_path": rel(response_path), "raw_response_sha256": sha(response_path),
                "sva_path": rel(sva_path), "sva_sha256": sha(sva_path),
            }
    for row in all_sets:
        row.update(generation_by_candidate[row["candidate_id"]])
    iverilog_version = execute(["iverilog", "-V"], timeout=10)
    vvp_version = execute(["vvp", "-V"], timeout=10)
    manifest = {"protocol": "behavioral_probes_v3", "status": "probe_evidence_only_no_dominance_pairs",
                "seed": SEED, "shared_pool_target_per_parent": POOL_TARGET,
                "query_budget_per_parent_per_policy": BUDGET,
                "policies": ["random_legal", "disagreement_guided"],
                "tp_definition": "buggy fail > 0 and correct fail == 0 for same-root mutation under selected stimulus",
                "fp_definition": "correct fail > 0 under selected legal stimulus",
                "tool_versions": {"iverilog": iverilog_version, "vvp": vvp_version},
                "parents": len(results), "candidates": len(all_sets) // 2,
                "candidate_policy_records": all_sets, "parent_results": results,
                "dominance_pairs_constructed": False}
    dump(OUT / "probe_manifest.json", manifest)
    print(json.dumps({"parents": len(results), "candidates": len(all_sets) // 2,
                      "policy_records": len(all_sets), "dominance_pairs_constructed": False}))


if __name__ == "__main__":
    main()
