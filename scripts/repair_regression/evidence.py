"""Independent behavior labels and append-only, candidate-independent evidence."""
import copy
from pathlib import Path
from obligation_evidence_monitor import check_inputs
from .cases import metadata
from .contracts import append, digest, file_hash, lines, read, record, validate, write


def adjudicate(c, obligations, rows, run, provenance):
    """No candidate argument or checker result is read by this function."""
    d, key = metadata(c), c["case_id"]
    trace = run["trace"]
    invalid = check_inputs(d, rows)
    complete = run["status"] == "ok" and not invalid and len(trace) == len(rows)
    epoch, was_reset, item_start, prev, epoch_start = 0, False, None, None, 0
    result = []
    for i in range(len(rows)):
        inp = rows[i]
        reset = not inp[d["rst"]]
        if reset:
            if not was_reset:
                epoch += 1
                epoch_start = i
            item_start, prev, was_reset = None, None, True
            continue
        was_reset = False
        row = trace[i] if i < len(trace) else {}
        actual, expected = None, None
        if key == "onehot":
            branch = "multihot" if inp["oh_i"].bit_count() > 1 else "zero_or_onehot"
            ids = [obligations[0]["obligation_id"]]
            if branch == "multihot":
                actual, expected = row.get("err_o"), 1
            tx = f"onehot:e{epoch}:sample{i}"
        else:
            branch = "present_stalled" if inp["push_i"] and not inp["pop_i"] else "present_accepted" if inp["push_i"] else "idle"
            ids = ["fifo.nonempty_when_present" if inp["push_i"] else "fifo.empty_when_idle"]
            actual, expected = row.get("empty_o"), int(not inp["push_i"])
            if inp["push_i"] and not (prev and prev["push_i"] and not prev["pop_i"]):
                item_start = i
            tx = f"fifo:e{epoch}:item{item_start}" if inp["push_i"] else f"fifo:e{epoch}:idle{i}"
        # Per-sample combinational scope: earlier violations do not relabel this sample.
        label = "legal" if expected is None or actual == expected else "target_violation"
        reason = None
        if not complete or (expected is not None and actual is None):
            label = "unknown"
            reason = "invalid_environment" if invalid else run.get("reason") or "missing_response"
        alignment = "not_applicable" if expected is None else "matched"
        if label == "unknown":
            alignment = ("extra_response" if len(trace) > len(rows) else
                         "missing_response" if i >= len(trace) else "unalignable")
        behavior = [{n: r.get(n) for n in [d["rst"], *d["inputs"], *d["outputs"]]} for r in trace[epoch_start:i+1]]
        # Include stimulus even when trace is absent; identical candidate/strategy rediscovery merges.
        behavior_hash = digest([rows[epoch_start:i+1], behavior])
        identity = digest([key, c["parameters"], behavior_hash, ids, "sampled_repair_scope_v1"])
        folder = Path(run["run"])
        result.append(record("Evidence", evidence_id=identity, revision=1, previous_revision_hash=None,
            revision_reason="independent_adjudication", case_id=key, obligation_ids=ids, branch=branch,
            sources=[{**provenance, "rtl_version": run["variant"], "run": str(folder)}], rtl_version=run["variant"],
            input_hash=run["input_hash"], config_hash=digest(c), behavior_hash=behavior_hash, label=label,
            scope="same-sample repair obligations only; no assertion on reset or untriggered DUT responses",
            judge=dict(reference="repair_regression.evidence.adjudicate", version="1.0", sha256=file_hash(__file__),
                       obligation_hash=digest(obligations), basis=[o["sources"] for o in obligations if o["obligation_id"] in ids],
                       input_legality_errors=invalid, trace_hash=digest(trace)), unknown_reason=reason,
            transaction=dict(reset_epoch=epoch, transaction_id=tx, trigger_cycle=i, deadline_cycle=i,
                             response_cycle=i if i < len(trace) else None, actual_response=actual,
                             expected_response=expected, alignment=alignment),
            artifacts=dict(stimulus=str(folder / "stimulus.json"), waveform=str(folder / "wave.vcd"),
                           trace=str(folder / "trace.json"), log=str(folder / "simulate.stdout"),
                           reproduce=str(folder / "reproduce.sh"), run=str(folder))))
        prev = inp
    return result


class EvidenceStore:
    def __init__(self, folder):
        self.path = Path(folder) / "evidence.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.current = {}
        for row in lines(self.path):
            validate("Evidence", row)
            previous = self.current.get(row["evidence_id"])
            if previous:
                if row["revision"] != previous["revision"] + 1 or row["previous_revision_hash"] != digest(previous):
                    raise ValueError("Broken evidence revision chain")
            elif row["revision"] != 1 or row["previous_revision_hash"] is not None:
                raise ValueError("Missing evidence revision")
            self.current[row["evidence_id"]] = row

    def add(self, row, revision_reason=None):
        validate("Evidence", row)
        old = self.current.get(row["evidence_id"])
        if old:
            if old["config_hash"] != row["config_hash"]:
                raise ValueError("Cannot merge evidence from incompatible case configurations")
            if old["label"] != row["label"] or old["judge"]["obligation_hash"] != row["judge"]["obligation_hash"]:
                if not revision_reason:
                    append(self.path.parent / "label_conflicts.jsonl", dict(old=old, proposed=row, status="unresolved"))
                    raise ValueError("Evidence label/semantic conflict; explicit revision reason required")
            else:
                merged = old["sources"] + [s for s in row["sources"] if s not in old["sources"]]
                if merged == old["sources"]:
                    return old
                row = {**copy.deepcopy(old), "sources": merged}
            row = {**row, "revision": old["revision"] + 1, "previous_revision_hash": digest(old),
                   "revision_reason": revision_reason or "merge_discovery_provenance"}
        validate("Evidence", row)
        append(self.path, row)
        self.current[row["evidence_id"]] = row
        return row

    def snapshot(self):
        rows = sorted(self.current.values(), key=lambda e: e["evidence_id"])
        ident = digest(rows)
        write(self.path.parent / "snapshots" / (ident + ".json"), rows)
        return ident, rows
