"""Controlled mechanism qualification, separate from actual pipeline proposals."""
import copy
import sys
import uuid
from pathlib import Path
from .backend import Backend, command
from .cases import metadata
from .contracts import digest, file_hash, read, validate, write
from .evidence import EvidenceStore, adjudicate
from .refinement import assertion, make_set, initial, attempt, replay, gate, attributable


def qualify(c, obligations, out):
    folder = out / "qa" / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True)
    store, backend = EvidenceStore(out), Backend(c, out)
    snapshot = store.snapshot()
    current = read(out / "assertion_set.json")
    results = []

    def check(name, condition, details=None):
        results.append(dict(name=name, passed=bool(condition), details=details))
        write(folder / "progress.json", results)

    baseline = replay(c, obligations, current, snapshot, backend, folder / "baseline")
    check("current_replay_is_complete", baseline["status"] == "complete")
    witness = next(e for e in snapshot[1] if e["label"] == "target_violation")
    cc = dict(cycle=witness["transaction"]["deadline_cycle"], trigger=1, fail=1)
    unrelated = assertion("qa.unrelated", witness["obligation_ids"], "1", "0", source="controlled_QA")
    check("coincident_unrelated_alarm_is_not_detection", not attributable(unrelated, witness, cc))
    delayed = copy.deepcopy(current["assertions"][-1])
    delayed["delay"] = 1
    check("latency_mismatch_is_not_aligned_away", not attributable(delayed, witness, cc))
    # Add a deliberately too-strong rule without changing existing detections.
    if c["case_id"] == "onehot":
        bad = assertion("qa.false_positive", [obligations[0]["obligation_id"]], "popcount(oh_i) <= 1", "!err_o", source="controlled_QA")
    else:
        bad = assertion("qa.false_positive", ["fifo.nonempty_when_present"], "push_i", "empty_o", source="controlled_QA")
    p = make_set(c, obligations, current["assertions"] + [bad], current["version"] + 1, "controlled_QA_new_false_positive")
    a, _ = attempt(c, obligations, current, p, snapshot, backend, folder / "new_false_positive", "controlled_QA")
    check("new_legal_false_positive_rejected", not a["accepted"] and any(s.startswith("new_legal_false_positive:") for s in a["reasons"]), a)
    weak = initial(c, obligations)
    a, _ = attempt(c, obligations, current, weak, snapshot, backend, folder / "lost_detection", "controlled_QA")
    check("lost_target_detection_rejected", not a["accepted"] and any(s.startswith("lost_target_detection:") for s in a["reasons"]), a)
    a, _ = attempt(c, obligations, weak, current, snapshot, backend, folder / "valid_improvement", "controlled_QA")
    before = read(a["old_replay"])
    after = read(a["proposal_replay"])
    check("preserving_improvement_accepted", a["accepted"] and after["summary"]["misses"] < before["summary"]["misses"], a)
    # A set with an initial FP may accept a correction preserving prior detections.
    a, _ = attempt(c, obligations, p, current, snapshot, backend, folder / "remove_existing_false_positive", "controlled_QA")
    check("existing_false_positive_can_be_removed", a["accepted"], a)
    if c["case_id"] == "fifo":
        idle = make_set(c, obligations, [assertion("qa.idle", ["fifo.empty_when_idle"], "!push_i", "empty_o", source="controlled_QA")])
        present = make_set(c, obligations, [assertion("qa.present", ["fifo.nonempty_when_present"], "push_i", "!empty_o", source="controlled_QA")])
        # Each obligation has genuine triggers; only idle has a violation in this RTL pair.
        checks = []
        for name, subset in [("idle", idle), ("present", present)]:
            r = replay(c, obligations, subset, snapshot, backend, folder / ("complementary_" + name))
            checks.append({e["evidence_id"] for e in r["evaluations"] if e["triggered_by"]})
        together = {e["evidence_id"] for e in baseline["evaluations"] if e["triggered_by"]}
        check("complementary_assertions_cover_both_obligations", all(checks) and not checks[0] & checks[1] and checks[0] | checks[1] == together)
    malformed = copy.deepcopy(current)
    malformed["assertions"][0] = assertion("qa.unsupported", [obligations[0]["obligation_id"]], "$past(oh_i)", "1", source="controlled_QA")
    rr = replay(c, obligations, malformed, snapshot, backend, folder / "unsupported")
    ok, why = gate(baseline, rr)
    check("unsupported_is_not_success", not ok and rr["summary"]["unknown"] == len(snapshot[1]), why)
    for status in ("unknown", "timeout", "error"):
        # Controlled status injection tests acceptance policy independently of tool behavior.
        uncertain = copy.deepcopy(baseline)
        uncertain["status"] = "incomplete"
        uncertain["evaluations"][0]["status"] = status
        ok, why = gate(baseline, uncertain)
        check(status + "_blocks_preservation", not ok, why)
    changed = copy.deepcopy(baseline)
    changed["snapshot_hash"] = digest("different_snapshot")
    check("different_snapshot_rejected", not gate(baseline, changed)[0])
    zero = make_set(c, obligations, [assertion("qa.vacuous", [obligations[0]["obligation_id"]], "0", "1", source="controlled_QA")])
    rr = replay(c, obligations, zero, snapshot, backend, folder / "vacuous")
    check("vacuous_proposal_rejected", not gate(baseline, rr)[0])
    changed = copy.deepcopy(current)
    changed["environment_hash"] = digest("narrowed legal environment")
    rr = replay(c, obligations, changed, snapshot, backend, folder / "changed_environment")
    check("environment_change_rejected", not gate(baseline, rr)[0])
    reload_result = replay(c, obligations, current, EvidenceStore(out).snapshot(), backend, folder / "reload")
    check("save_reload_and_actual_RTL_replay_identical", reload_result["evaluations"] == baseline["evaluations"])
    isolated = EvidenceStore(folder / "store_qualification")
    evidence = copy.deepcopy(snapshot[1][0])
    # Start a new independent QA journal with its own first revision.
    evidence.update(revision=1, previous_revision_hash=None, revision_reason="controlled_QA_copy")
    isolated.add(evidence)
    isolated.add(evidence)
    check("duplicate_discovery_deduplicated", len(isolated.current) == 1 and next(iter(isolated.current.values()))["revision"] == 1)
    conflict = copy.deepcopy(evidence)
    conflict["label"] = "unknown"
    conflict["unknown_reason"] = "controlled_QA_label_conflict"
    rejected = False
    try:
        isolated.add(conflict)
    except ValueError:
        rejected = True
    check("label_conflict_not_silently_overwritten", rejected and next(iter(isolated.current.values()))["label"] == evidence["label"])
    isolated.add(conflict, "controlled_QA_explicit_revision")
    check("label_revision_history_retained", EvidenceStore(folder / "store_qualification").current[evidence["evidence_id"]]["revision"] == 2)
    invalid = copy.deepcopy(current)
    invalid["unexpected_field"] = True
    try:
        validate("AssertionSet", invalid)
        strict = False
    except Exception:
        strict = True
    check("strict_schema_rejects_extra_fields", strict)
    timeout_dir = folder / "real_timeout"
    timeout_dir.mkdir()
    timed = command([sys.executable, "-c", "import time; time.sleep(2)"], timeout_dir, "controlled_timeout", .02)
    check("real_subprocess_timeout_recorded", timed["status"] == "timeout", timed)
    if c["case_id"] == "onehot":
        checker_qualification(c, obligations, backend, folder, check)
    result = dict(schema_version="1.0", source="controlled_engineering_QA; separate from generation/refinement claims",
                  passed=all(r["passed"] for r in results), checks=results, path=str(folder))
    write(folder / "result.json", result)
    write(out / "qa/result.json", result)
    return dict(passed=result["passed"], checks=len(results), failed=[r["name"] for r in results if not r["passed"]], path=str(folder))


def checker_qualification(c, obligations, backend, folder, check):
    d = metadata(c)
    # Repeated triggers, captured history, reset cancellation, exact delay 0/1/2.
    values = [(0, 0), (0, 0), (1, 1), (1, 1), (1, 0), (0, 0), (1, 1), (1, 0), (1, 0), (1, 0)]
    rows = [dict(cycle=i, stimulus_id=f"qa:{i}", rst_n=r, oh_i=v, addr_i=0, en_i=1) for i, (r, v) in enumerate(values)]
    for delay in (0, 1, 2):
        a = assertion("qa.delay", [obligations[0]["obligation_id"]], "oh_i == 1", "p1_oh_i == 1", delay, source="controlled_checker_QA")
        aset = make_set(c, obligations, [a])
        run = backend.execute(rows, "fixed", aset, namespace=str(folder.relative_to(backend.out) / f"delay_{delay}"))
        pending, prev, expected = {}, 0, []
        for i, row in enumerate(rows):
            if not row["rst_n"]:
                pending.clear()
                prev = 0
                continue
            trigger = int(row["oh_i"] == 1)
            if trigger:
                pending[i + delay] = i
            due = pending.pop(i, None)
            expected.append(dict(cycle=i, trigger=trigger, fail=int(due is not None and prev != 1)))
            prev = row["oh_i"]
        check(f"sample_history_delay_{delay}_and_reset", run["status"] == "ok" and run["checks"].get("0") == expected,
              dict(run=run["run"], expected=expected))
    vals = [(0, 0), (1, 2), (1, 2), (1, 0), (1, 0)]
    rows = [dict(cycle=i, stimulus_id=f"pulse:{i}", rst_n=r, oh_i=v, addr_i=0, en_i=1) for i, (r, v) in enumerate(vals)]
    a = assertion("qa.async", [obligations[0]["obligation_id"]], "1", "p1_oh_i == 0", source="controlled_checker_QA")
    marker = "\n".join(f"{n}={rows[3][n]};" for n in [d["rst"], *d["inputs"]])
    def pulse(text):
        return text.replace(marker, marker + "\n#1 rst_n=0; #1 rst_n=1;", 1)
    run = backend.execute(rows, "fixed", make_set(c, obligations, [a]),
                          namespace=str(folder.relative_to(backend.out) / "between_edge_reset"), tb_transform=pulse)
    event = next((e for e in run["checks"].get("0", []) if e["cycle"] == 3), {})
    check("between_edge_reset_clears_history", run["status"] == "ok" and event.get("fail") == 0, run["run"])
    a = assertion("qa.async_pending", [obligations[0]["obligation_id"]], "oh_i == 2", "0", delay=1, source="controlled_checker_QA")
    run = backend.execute(rows, "fixed", make_set(c, obligations, [a]),
                          namespace=str(folder.relative_to(backend.out) / "between_edge_pending_cancel"), tb_transform=pulse)
    event = next((e for e in run["checks"].get("0", []) if e["cycle"] == 3), {})
    check("between_edge_reset_cancels_pending_response", run["status"] == "ok" and event.get("fail") == 0, run["run"])
    # Actual X propagation in RTL, retained as unknown behavior evidence in QA only.
    def unknown(text):
        return text.replace('initial begin\n$dumpfile', "initial begin\nforce dut.err_o = 1'bx;\n$dumpfile", 1)
    run = backend.execute(rows, "fixed", namespace=str(folder.relative_to(backend.out) / "four_state"), tb_transform=unknown)
    ev = adjudicate(c, obligations, rows, run, dict(search_type="controlled_QA", seed=0))
    write(folder / "unknown_evidence.json", ev)
    check("actual_four_state_trace_retained_unknown", run["status"] == "unknown" and ev and all(e["label"] == "unknown" for e in ev), run["run"])
