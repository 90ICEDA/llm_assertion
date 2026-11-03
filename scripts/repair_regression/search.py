"""Three explicitly distinct bounded search operations, deterministic round robin."""
from collections import Counter
from pathlib import Path
import obligation_search_policy as policy
from .cases import metadata
from .contracts import append, digest, read, write
from .evidence import adjudicate
from .refinement import replay

KINDS = ("repair_difference", "legal_boundary", "obligation_gap")


def stimuli(c, kind, seed, step, target):
    d = metadata(c)
    if kind == "repair_difference":
        if step % 3 == 0:
            return policy.guided(d, seed, step)
        if step % 3 == 1:
            return policy.ordinary(d, seed)
        return policy.disagreement(d, seed, policy.guided(d, seed, step))
    if kind == "legal_boundary":
        rows = policy.guided(d, seed, 1)
        # Reset during a presented/stalled item, release, continuous transfers.
        rows[9][d["rst"]] = 0
        rows[10][d["rst"]] = 0
        rows[11][d["rst"]] = 1
        if c["case_id"] == "onehot":
            rows[2].update(oh_i=0, en_i=1, addr_i=0)
            rows[3].update(oh_i=1, en_i=1, addr_i=2)
        else:
            for i in (4, 5, 6):
                rows[i].update(push_i=1, pop_i=0, data_i=73)
            rows[7].update(push_i=1, pop_i=1, data_i=73)
            rows[8].update(push_i=1, pop_i=1, data_i=91)
        return policy.repair_environment(d, rows)
    rows = policy.guided(d, seed, step)
    if c["case_id"] == "onehot":
        # Force genuine multihot cases outside the literal-3 starting seed.
        for i, value in enumerate((6, 10, 12, 5, 9, 15), 2):
            rows[i].update(oh_i=value, en_i=1, addr_i=(value & -value).bit_length() - 1)
    elif target == "fifo.empty_when_idle":
        for i in range(2, 7):
            rows[i].update(push_i=0, pop_i=i % 2)
    else:
        for i in range(2, 7):
            rows[i].update(push_i=1, pop_i=int(i == 6), data_i=73)
    return policy.repair_environment(d, rows)


def select_target(obligations, previous):
    if previous:
        for e in previous["evaluations"]:
            if e["miss"]:
                return e["obligation_ids"][0]
        seen = {o for e in previous["evaluations"] if e["triggered_by"] for o in e["obligation_ids"]}
        for o in obligations:
            if o["obligation_id"] not in seen:
                return o["obligation_id"]
    return obligations[0]["obligation_id"]


def search(c, obligations, current, store, backend, *, kind, seed, step, target, folder):
    """Same signature for all three operations; even no-witness runs persist."""
    if kind not in KINDS:
        raise ValueError(kind)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "search.json").exists():
        return read(folder / "search.json")
    rows = stimuli(c, kind, seed, step, target)
    prov = dict(search_type=kind, seed=seed, target_obligation=target, search_id=str(folder))
    write(folder / "started.json", {**prov, "input_hash": digest(rows), "status": "running"})
    pair, acquired = {}, []
    for variant in ("buggy", "fixed"):
        r = backend.execute(rows, variant)  # Deliberately candidate-free label acquisition.
        pair[variant] = r
        for e in adjudicate(c, obligations, rows, r, prov):
            acquired.append(store.add(e))
    # Deduplicate the temporary replay snapshot, too.
    acquired = sorted({e["evidence_id"]: store.current[e["evidence_id"]] for e in acquired}.values(), key=lambda e: e["evidence_id"])
    rr = replay(c, obligations, current, (digest(acquired), acquired), backend, folder / "candidate_evaluation")
    both_ok = all(r["status"] == "ok" for r in pair.values())
    differences = []
    if both_ok:
        for a, b in zip(pair["buggy"]["trace"], pair["fixed"]["trace"]):
            if any(a.get(n) != b.get(n) for n in c["signals"]["outputs"]):
                differences.append(a["cycle"])
    witnesses = [e["evidence_id"] for e in rr["evaluations"] if
        (e["miss"] and target in e["obligation_ids"] if kind == "obligation_gap" else
         e["false_positive"] if kind == "legal_boundary" else
         e["label"] == "target_violation" and e["transaction"]["deadline_cycle"] in differences)]
    result = {**prov, "schema_version": "1.0", "status": "completed" if both_ok else "incomplete", "executions": 2,
        "input_hash": digest(rows), "runs": {k: r["run"] for k, r in pair.items()},
        "run_statuses": {k: r["status"] for k, r in pair.items()}, "difference_cycles": differences,
        "difference_is_bug": False, "witnesses": witnesses, "labels": dict(Counter(e["label"] for e in acquired)),
        "candidate_evaluation": str(folder / "candidate_evaluation/result.json"),
        "stop_reason": "witness_found_within_query" if witnesses else "no_witness_in_this_bounded_query",
        "transaction_overlap": "not_applicable_to_Depth0_storage; successive/stalled presentations exercised" if c["case_id"] == "fifo" else "independent_each_sample"}
    write(folder / "search.json", result)
    return result
