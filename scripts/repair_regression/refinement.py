"""Recorded template proposals and evidence-preserving set acceptance."""
import copy
import difflib
from collections import Counter
from pathlib import Path
from jsonschema import ValidationError
import contract_v3_checker as checker
from repair_contract_cases import controlled_candidate
from .backend import validate_assertions
from .cases import metadata
from .contracts import digest, read, record, validate, write


def assertion(ident, ids, ant, cons, delay=0, version=1, source="offline_obligation_template_v1"):
    return dict(assertion_id=ident, version=version, obligation_ids=ids, antecedent=ant, consequent=cons,
                delay=delay, authorized_history_depth=3, source=source, tool_support="restricted_monitor",
                content_hash=digest(dict(antecedent=ant, consequent=cons, delay=delay)))


def make_set(c, obligations, assertions, version=1, source="offline_template; not a model call"):
    return record("AssertionSet", set_id=c["case_id"] + ".repair", case_id=c["case_id"], version=version,
                  contract_hash=digest(obligations), environment_hash=digest(c["environment"]), assertions=assertions, source=source)


def initial(c, obligations):
    # Explicit partial seeds exercise concrete gap-driven refinement; no claimed LLM provenance.
    if c["case_id"] == "onehot":
        a = assertion("onehot.multihot", [obligations[0]["obligation_id"]], "oh_i == 3", "err_o")
    else:
        a = assertion("fifo.present", ["fifo.nonempty_when_present"], "push_i", "!empty_o")
    return make_set(c, obligations, [a], source="offline_partial_seed_v1; engineered starting point, not model output")


def propose(c, obligations, current, replay):
    feedback = [e for e in replay["evaluations"] if e["miss"] or e["false_positive"]]
    if not feedback:
        return None
    cs = copy.deepcopy(current["assertions"])
    if c["case_id"] == "onehot":
        # Reuse the existing engineering template only as a proposal, not acceptance truth.
        template = controlled_candidate("onehot")
        cs = [assertion("onehot.multihot", [obligations[0]["obligation_id"]], template["antecedent"],
                        template["consequent"], version=current["version"] + 1,
                        source="repair_contract_cases.controlled_candidate: offline template proposal")]
    else:
        if not any(a["assertion_id"] == "fifo.idle" for a in cs):
            cs.append(assertion("fifo.idle", ["fifo.empty_when_idle"], "!push_i", "empty_o"))
        else:
            return None
    return make_set(c, obligations, cs, current["version"] + 1)


def precheck(c, obligations, aset):
    validate("AssertionSet", aset)
    if aset["case_id"] != c["case_id"] or aset["contract_hash"] != digest(obligations) or aset["environment_hash"] != digest(c["environment"]):
        raise ValueError("Contract/environment/case changed")
    if not aset["assertions"] or len({a["assertion_id"] for a in aset["assertions"]}) != len(aset["assertions"]):
        raise ValueError("Empty set or duplicate assertion IDs")
    ids = {o["obligation_id"] for o in obligations}
    for a in aset["assertions"]:
        if not a["obligation_ids"] or not set(a["obligation_ids"]) <= ids:
            raise ValueError("Unknown obligation ID")
    validate_assertions(c, aset)


def attributable(a, e, check):
    """Conservative exact-response certificate, beyond coincident alarm counting.

    Only same-sample checks of the actual obligated output are credited. Arbitrary
    expressions and delayed matches remain unverified, even when their alarm coincides.
    """
    if a["delay"] != 0 or not check or check["trigger"] != 1 or check["fail"] != 1:
        return False
    if not set(a["obligation_ids"]) & set(e["obligation_ids"]):
        return False
    cons = a["consequent"].replace(" ", "").replace("(", "").replace(")", "")
    certified = {"onehot.multihot_detect": {"err_o", "err_o==1"},
                 "fifo.empty_when_idle": {"empty_o", "empty_o==1"},
                 "fifo.nonempty_when_present": {"!empty_o", "empty_o==0"}}
    return (e["transaction"]["alignment"] == "matched" and
            e["transaction"]["trigger_cycle"] == e["transaction"]["deadline_cycle"] == check["cycle"] and
            any(cons in certified.get(oid, set()) for oid in e["obligation_ids"]))


def replay(c, obligations, aset, snapshot, backend, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    sid, evidence = snapshot
    if sid != digest(evidence):
        raise ValueError("Snapshot hash mismatch")
    pre_error = None
    try:
        precheck(c, obligations, aset)
    except (ValueError, AssertionError, KeyError, TypeError, ValidationError) as e:
        pre_error = str(e)
    grouped, runs, evaluations = {}, [], []
    for e in evidence:
        raw = e["artifacts"]["run"]
        if raw not in grouped and not pre_error and e["label"] != "unknown":
            rows = read(e["artifacts"]["stimulus"])
            if digest(rows) != e["input_hash"] or e["config_hash"] != digest(c) or e["judge"]["obligation_hash"] != digest(obligations):
                raise ValueError("Evidence input/config/semantics changed")
            r = backend.execute(rows, e["rtl_version"], aset, namespace=str(folder.relative_to(backend.out) / "simulations"))
            # Re-run original RTL, then compare exact timing/values with saved trace.
            if r["status"] == "ok" and digest(r["trace"]) != e["judge"]["trace_hash"]:
                r = {**r, "status": "unknown", "reason": "behavior_changed_on_replay"}
            grouped[raw] = r
            runs.append(r["run"])
        r = grouped.get(raw)
        status = "unknown" if e["label"] == "unknown" else "unsupported" if pre_error else r["status"]
        per_assertion, triggered, detected = [], [], []
        cycle = e["transaction"]["deadline_cycle"]
        if status == "ok":
            for j, a in enumerate(aset["assertions"]):
                cc = next((x for x in r["checks"].get(str(j), []) if x["cycle"] == cycle), None)
                if not cc or cc["fail"] is None or cc["trigger"] is None:
                    status = "unknown"
                    continue
                certified = e["label"] == "target_violation" and attributable(a, e, cc)
                if certified:
                    detected.append(a["assertion_id"])
                if (cc["trigger"] and e["transaction"]["expected_response"] is not None
                        and set(a["obligation_ids"]) & set(e["obligation_ids"])):
                    triggered.append(a["assertion_id"])
                per_assertion.append(dict(assertion_id=a["assertion_id"], version=a["version"], content_hash=a["content_hash"],
                    trigger=bool(cc["trigger"]), failed=bool(cc["fail"]), valid_detection=certified,
                    attribution="exact_same_sample_output_response" if certified else "uncredited"))
        evaluations.append(dict(evidence_id=e["evidence_id"], label=e["label"], obligation_ids=e["obligation_ids"],
            branch=e["branch"], transaction=e["transaction"], status=status,
            reason=e["unknown_reason"] or pre_error or (r.get("reason") if r else None), assertions=per_assertion,
            triggered_by=triggered, detected_by=detected,
            false_positive=status == "ok" and e["label"] == "legal" and any(a["failed"] for a in per_assertion),
            miss=status == "ok" and e["label"] == "target_violation" and not detected))
    result = record("ReplayResult", case_id=c["case_id"], snapshot_hash=sid, assertion_set_hash=digest(aset),
        backend="iverilog_restricted_procedural_monitor" if c["tool_config"]["backend"] == "iverilog" else "none:unsupported_formal_backend",
        status="complete" if all(e["status"] == "ok" for e in evaluations) else "incomplete",
        evaluations=evaluations, runs=runs, summary=dict(evidence=len(evaluations),
            labels=dict(Counter(e["label"] for e in evaluations)), false_positives=sum(e["false_positive"] for e in evaluations),
            misses=sum(e["miss"] for e in evaluations), detected=sum(bool(e["detected_by"]) for e in evaluations),
            unknown=sum(e["status"] != "ok" for e in evaluations), statuses=dict(Counter(e["status"] for e in evaluations))))
    write(folder / "result.json", result)
    return result


def gate(old, new):
    reasons = []
    if old["snapshot_hash"] != new["snapshot_hash"]:
        reasons.append("different_evidence_snapshots")
    before = {e["evidence_id"]: e for e in old["evaluations"]}
    after = {e["evidence_id"]: e for e in new["evaluations"]}
    if before.keys() != after.keys() or not before:
        reasons.append("different_or_empty_evidence_population")
    if old["status"] != "complete" or new["status"] != "complete" or any(e["status"] != "ok" for e in [*before.values(), *after.values()]):
        reasons.append("unknown_error_timeout_or_unsupported_cannot_prove_preservation")
    for ident in before.keys() & after.keys():
        a, b = before[ident], after[ident]
        if b["false_positive"] and not a["false_positive"]:
            reasons.append("new_legal_false_positive:" + ident)
        if a["detected_by"] and not b["detected_by"]:
            reasons.append("lost_target_detection:" + ident)
        if a["triggered_by"] and not b["triggered_by"]:
            reasons.append("lost_trigger_coverage:" + ident)
    if not any(e["triggered_by"] for e in after.values()):
        reasons.append("vacuous_no_effective_trigger")
    return not reasons, reasons


def attempt(c, obligations, current, proposal, snapshot, backend, folder, source="offline_template"):
    folder.mkdir(parents=True, exist_ok=True)
    write(folder / "old.json", current)
    write(folder / "proposal.json", proposal)
    diff = "".join(difflib.unified_diff(emit_sva(c, current).splitlines(True), emit_sva(c, proposal).splitlines(True), "old.sv", "proposal.sv"))
    (folder / "changes.diff").write_text(diff)
    old = replay(c, obligations, current, snapshot, backend, folder / "old_replay")
    new = replay(c, obligations, proposal, snapshot, backend, folder / "proposal_replay")
    accepted, reasons = gate(old, new)
    result = record("RefinementAttempt", attempt_id=folder.name, case_id=c["case_id"], snapshot_hash=snapshot[0],
        old_set_hash=digest(current), proposal_hash=digest(proposal), source=source,
        feedback=[e for e in old["evaluations"] if e["false_positive"] or e["miss"]],
        old_replay=str(folder / "old_replay/result.json"), proposal_replay=str(folder / "proposal_replay/result.json"),
        diff=str(folder / "changes.diff"), accepted=accepted, reasons=reasons or ["all_snapshot_preservation_conditions_met"])
    write(folder / "attempt.json", result)
    return result, new if accepted else old


def emit_sva(c, aset):
    d = metadata(c)
    signals = {d["clk"]: 1, d["rst"]: 1, **d["inputs"], **d["outputs"]}
    decl = lambda n, w: "input logic " + (f"[{w-1}:0] " if w > 1 else "") + n
    name = "af_" + c["case_id"] + "_repair_checker"
    out = ["// Generated SVA for review/binding. Native SVA/formal validation NOT claimed.",
           "// Set hash: " + digest(aset), "module " + name + "(\n  " + ",\n  ".join(decl(n, w) for n, w in signals.items()) + "\n);"]
    # Explicit sampled, async-reset history is not native $past initialization.
    used = " ".join(a["antecedent"] + " " + a["consequent"] for a in aset["assertions"])
    import re
    history = sorted(set(re.findall(r"\bp[123]_(\w+)", used)))
    for n in history:
        w = signals[n]
        for i in (1, 2, 3):
            out.append("logic " + (f"[{w-1}:0] " if w > 1 else "") + f"p{i}_{n};")
        out.append(f'always @(posedge {d["clk"]} or negedge {d["rst"]}) begin')
        out.append(f'if (!{d["rst"]}) begin p1_{n} <= 0; p2_{n} <= 0; p3_{n} <= 0; end')
        out.append(f'else begin p1_{n} <= {n}; p2_{n} <= p1_{n}; p3_{n} <= p2_{n}; end end')
    functions, props = set(), []
    for a in aset["assertions"]:
        try:
            z, rules = checker.normalize(a, d, a["authorized_history_depth"])
        except (AssertionError, ValueError):
            props.append("// Unsupported proposal retained in JSON: " + a["assertion_id"])
            continue
        functions.update(r["width"] for r in rules)
        ident = re.sub(r"\W", "_", a["assertion_id"])
        op = "|->" if not a["delay"] else "|=>" if a["delay"] == 1 else "|-> ##2"
        props += [f'// {a["assertion_id"]} v{a["version"]}; obligations: {", ".join(a["obligation_ids"])}; source: {a["source"]}',
                  f'{ident}: assert property (@(posedge {d["clk"]}) disable iff (!{d["rst"]}) ({z["antecedent"]}) {op} ({z["consequent"]}));']
    out += [checker.count_function(w) for w in sorted(functions)] + props + ["endmodule"]
    out.append(f'bind {d["module"]} {name} af_repair_instance (' + ", ".join(f".{n}({n})" for n in signals) + ");")
    return "\n".join(out) + "\n"
