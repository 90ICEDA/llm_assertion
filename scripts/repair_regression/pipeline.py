"""The shared onehot/FIFO run, recovery, and independent replay loop."""
import argparse
import copy
from collections import Counter
from pathlib import Path
import sys
import uuid
from .backend import Backend, preflight
from .cases import example, extract, freeze, load_case
from .contracts import ROOT, digest, export_schemas, file_hash, lines, read, record, validate, write
from .evidence import EvidenceStore
from .refinement import initial, propose, attempt, replay, emit_sva
from .search import KINDS, search, select_target


def implementation_manifest():
    files = [*Path(__file__).parent.glob("*.py"), ROOT / "scripts/run_repair_regression.py"]
    files += [ROOT / "scripts" / n for n in ["repair_contract_cases.py", "run_repair_contract.py", "contract_v3_checker.py",
                                             "obligation_evidence_monitor.py", "obligation_search_policy.py"]]
    return {str(p): file_hash(p) for p in sorted(files)}


def verify_run(out):
    saved = read(out / "implementation.json")
    if saved != implementation_manifest():
        raise ValueError("Implementation changed; start a new run instead of silently resuming different semantics")
    c = load_case(out / "case.json")
    import shutil
    probe = read(out / "tools/availability.json")
    for name in ("iverilog", "vvp"):
        p = shutil.which(c["tool_config"][name])
        if p and file_hash(p) != probe["executable_hashes"].get(name):
            raise ValueError("Simulator executable changed")
    obligations = read(out / "obligations.json")
    for o in obligations:
        validate("Obligation", o)
    if digest(obligations) != read(out / "state.json")["obligation_hash"]:
        raise ValueError("Obligations changed")
    return c, obligations


def coverage(obligations, rr):
    result = []
    for o in obligations:
        ev = [e for e in rr["evaluations"] if o["obligation_id"] in e["obligation_ids"]]
        branches = []
        for branch in o["branches"]:
            bs = [e for e in ev if e["branch"] == branch]
            triggered = sum(bool(e["triggered_by"]) for e in bs)
            violations = sum(e["label"] == "target_violation" for e in bs)
            detected = sum(bool(e["detected_by"]) for e in bs)
            branches.append(dict(branch=branch, samples=len(bs), trigger_samples=triggered,
                target_violations=violations, detected=detected, missed=sum(e["miss"] for e in bs),
                unknown=sum(e["status"] != "ok" for e in bs),
                gap="unobserved_branch" if not bs else "no_effective_trigger" if not triggered else
                    "missed_target_violation" if detected < violations else None,
                detection_validation="witnessed" if detected else "no_target_violation_witness; protection not mutation-proven"))
        result.append(dict(obligation_id=o["obligation_id"], branches=branches))
    return result


def finalize(c, obligations, current, store, backend, out, state):
    snapshot = store.snapshot()
    rr = replay(c, obligations, current, snapshot, backend, out / "final_replay")
    write(out / "assertion_set.json", current)
    (out / "assertions.sv").write_text(emit_sva(c, current), encoding="utf-8")
    searches = [read(p) for p in sorted((out / "search").glob("*/*/search.json"))]
    attempts = [read(p) for p in sorted((out / "refinement").glob("*/attempt.json"))]
    search_summary = {}
    for kind in KINDS:
        subset = [s for s in searches if s["search_type"] == kind]
        search_summary[kind] = dict(queries=len(subset), executions=sum(s["executions"] for s in subset),
            witnesses=sum(len(s["witnesses"]) for s in subset), no_witness=sum(not s["witnesses"] for s in subset),
            statuses=dict(Counter(s["status"] for s in subset)),
            unique_evidence=len({e["evidence_id"] for e in snapshot[1] if any(s["search_type"] == kind for s in e["sources"])}))
    cov = coverage(obligations, rr)
    preserved = all(a["accepted"] or a["reasons"] for a in attempts)
    passed = bool(snapshot[1]) and not any(rr["summary"][n] for n in ("false_positives", "misses", "unknown"))
    passed = passed and all(not b["gap"] for o in cov for b in o["branches"])
    tools = read(out / "tools/availability.json")
    result = record("Verdict", case_id=c["case_id"], config_hash=digest(c), rtl_hashes={v: {p: file_hash(p) for p in x["sources"]} for v, x in c["rtl"].items()},
        assertion_hash=digest(current), evidence_hash=snapshot[0], versions=dict(schema="1.0", assertions=current["version"],
            evidence_revisions=sum(e["revision"] for e in snapshot[1]), implementation=digest(read(out / "implementation.json"))),
        stages=dict(case_input="validated", extraction="imported_confirmed", candidate_generation=current["source"],
                    search="completed" if all(s["status"] == "completed" for s in searches) else "incomplete",
                    refinement="completed", replay=rr["status"], backend=c["tool_config"]["backend"], tools=tools),
        search=search_summary, obligations=cov, replay=rr["summary"], refinement=dict(
            accepted=sum(a["accepted"] for a in attempts), rejected=sum(not a["accepted"] for a in attempts),
            rounds_completed=state["completed_rounds"], controlled_QA="reported separately in qa/result.json"),
        evidence_preservation=bool(preserved and rr["status"] == "complete"), flow_completed=True, current_evidence_pass=bool(passed),
        bounded_search="Finite deterministic searches only; no proof of absence of counterexamples.",
        native_sva="not_executed: procedural monitor lowering only", formal_proof="not_proven; Jasper not invoked",
        stop_reason="configured_search_and_refinement_budget_exhausted", limitations=c["limitations"] + [
            "Only same-sample exact-output response certificates receive detection credit; arbitrary coincident failures do not.",
            "Stored legacy test sources are provenance; new deterministic schedules, not historical verdicts, drive this run.",
            "No violation witness on an obligation branch means its bug-detection strength remains unverified on that branch."],
        reproduce=f"python3 scripts/run_repair_regression.py replay --out {out}")
    write(out / "verdict.json", result)
    write(out / "interface_examples.json", {"CaseInput": str(out / "case.json"), "Obligation": str(out / "obligations.json"),
        "Evidence": str(out / "evidence.jsonl"), "AssertionSet": str(out / "assertion_set.json"),
        "ReplayResult": str(out / "final_replay/result.json"), "RefinementAttempt": str(out / "refinement"), "Verdict": str(out / "verdict.json")})
    return result


def run(args):
    out = Path(args.out).resolve()
    if args.resume:
        c, obligations = verify_run(out)
        state = read(out / "state.json")
        for name in ("seed", "search_budget", "rounds"):
            value = getattr(args, name)
            if value is not None and value != state[name]:
                raise ValueError("Resume budgets/seed are immutable; start a new run")
        if args.backend and args.backend != c["tool_config"]["backend"]:
            raise ValueError("Cannot change backend on resume")
        if args.case and digest(load_case(args.case)) != digest(read(out / "case.original.json")):
            raise ValueError("Resume case configuration changed")
        current = state.get("current", read(out / "assertion_set.json"))
    else:
        if not args.case:
            raise ValueError("--case is required for a new run")
        c = load_case(args.case)
        if args.backend:
            c["tool_config"]["backend"] = args.backend
        out.mkdir(parents=True, exist_ok=False)
        c = freeze(c, out)
        obligations = extract(c)
        write(out / "obligations.json", obligations)
        current = initial(c, obligations)
        write(out / "initial_assertion_set.json", current)
        write(out / "assertion_set.json", current)
        manifest = implementation_manifest()
        write(out / "implementation.json", manifest)
        for i, p in enumerate(manifest):
            target = out / "implementation_sources" / (str(i) + "_" + Path(p).name)
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(Path(p).read_bytes())
        state = dict(seed=args.seed if args.seed is not None else 20261014,
                     search_budget=args.search_budget if args.search_budget is not None else 6,
                     rounds=args.rounds if args.rounds is not None else 2, completed_rounds=0,
                     obligation_hash=digest(obligations))
        if state["search_budget"] < 3 or state["rounds"] < 1:
            raise ValueError("At least three queries per round and one refinement round are required")
        write(out / "state.json", state)
        preflight(c, out)
    backend, store = Backend(c, out), EvidenceStore(out)
    for round_no in range(state["completed_rounds"], state["rounds"]):
        previous = None
        if store.current:
            previous = replay(c, obligations, current, store.snapshot(), backend, out / "rounds" / str(round_no) / "before_search")
        for i in range(state["search_budget"]):
            kind = KINDS[i % len(KINDS)]
            target = select_target(obligations, previous)
            result = search(c, obligations, current, store, backend, kind=kind, seed=state["seed"] + round_no * 1000 + i,
                step=round_no * (state["search_budget"] // 3) + i // 3, target=target,
                folder=out / "search" / str(round_no) / f"{i:03d}_{kind}")
            previous = read(result["candidate_evaluation"])
            print(f'{c["case_id"]} round={round_no} {kind}: {result["status"]}, witnesses={len(result["witnesses"])}', flush=True)
        snapshot = store.snapshot()
        before = replay(c, obligations, current, snapshot, backend, out / "rounds" / str(round_no) / "before_refinement")
        proposal = propose(c, obligations, current, before)
        if proposal:
            folder = out / "refinement" / f"round_{round_no:03d}"
            if (folder / "attempt.json").exists():
                change = read(folder / "attempt.json")
                if change["snapshot_hash"] != snapshot[0] or change["old_set_hash"] != digest(current):
                    raise ValueError("Interrupted attempt snapshot/current mismatch")
                proposal = read(folder / "proposal.json")
            else:
                change, _ = attempt(c, obligations, current, proposal, snapshot, backend, folder)
            if change["accepted"]:
                current = proposal
            print(f'{c["case_id"]} refinement accepted={change["accepted"]}', flush=True)
        else:
            write(out / "rounds" / str(round_no) / "no_proposal.json", dict(reason="no_actionable_supported_template_gap", snapshot_hash=snapshot[0]))
        state["completed_rounds"] = round_no + 1
        # Single checkpoint contains the current set, allowing recovery across a pointer write.
        state["current"] = current
        write(out / "state.json", state)
        write(out / "assertion_set.json", current)
    return finalize(c, obligations, current, store, backend, out, state)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    examples = sub.add_parser("examples")
    examples.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--case")
    r.add_argument("--out", required=True)
    r.add_argument("--seed", type=int)
    r.add_argument("--search-budget", type=int)
    r.add_argument("--rounds", type=int)
    r.add_argument("--backend", choices=["iverilog", "jasper"])
    r.add_argument("--resume", action="store_true")
    r = sub.add_parser("replay")
    r.add_argument("--out", required=True)
    r.add_argument("--assertion-set")
    r = sub.add_parser("qa")
    r.add_argument("--out", required=True)
    args = p.parse_args()
    if args.action == "examples":
        folder = Path(args.out).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        for key in ("onehot", "fifo"):
            write(folder / (key + ".json"), example(key))
        export_schemas(folder / "schemas")
        print(folder)
        return 0
    if args.action == "run":
        result = run(args)
        print({k: result[k] for k in ("case_id", "flow_completed", "current_evidence_pass", "replay")})
        return 0 if result["current_evidence_pass"] else 2
    out = Path(args.out).resolve()
    c, obligations = verify_run(out)
    if args.action == "qa":
        from .qa import qualify
        result = qualify(c, obligations, out)
        print(result)
        return 0 if result["passed"] else 2
    aset = read(args.assertion_set or out / "assertion_set.json")
    folder = out / "independent_replays" / uuid.uuid4().hex[:12]
    rr = replay(c, obligations, aset, EvidenceStore(out).snapshot(), Backend(c, out), folder)
    same = rr["evaluations"] == read(out / "final_replay/result.json")["evaluations"] if not args.assertion_set else None
    write(folder / "comparison.json", dict(saved_and_reloaded_results_identical=same))
    print(dict(path=str(folder), summary=rr["summary"], saved_and_reloaded_results_identical=same))
    return 0 if rr["status"] == "complete" and same is not False else 2
