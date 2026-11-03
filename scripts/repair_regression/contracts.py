"""Versioned, closed JSON interfaces; jsonschema is the sole dependency."""
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator

VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[2]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def append(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")
        handle.flush()
        import os
        os.fsync(handle.fileno())


def lines(path):
    if not Path(path).exists():
        return []
    # Refuse truncated/corrupt journals, never silently discard evidence.
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


S = {"type": "string", "minLength": 1}
I = {"type": "integer", "minimum": 0}
B = {"type": "boolean"}
MAP = {"type": "object"}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def array(item=S):
    return {"type": "array", "items": item}


def enum(*values):
    return {"enum": list(values)}


def obj(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def versioned(kind, fields):
    return obj({"schema_version": {"const": VERSION}, "kind": {"const": kind}, **fields})


SOURCE = obj({"path": S, "sha256": HASH, "location": S, "basis": S})
RTL = obj({"sources": array(S), "include_dirs": array(S), "defines": array(S)})
CLOCK = obj({"signal": S, "event": {"const": "posedge_pre_NBA"}, "input_drive": {"const": "negedge"}})
RESET = obj({"signal": S, "active": {"const": 0}, "cancel_pending": {"const": True}, "initial_samples": I})
TOOL = obj({"backend": enum("iverilog", "jasper"), "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
            "iverilog": S, "vvp": S, "jasper": S, "model_url": S})
ASSERTION = obj({"assertion_id": S, "version": I, "obligation_ids": array(S), "antecedent": S,
                 "consequent": S, "delay": I, "authorized_history_depth": I, "source": S,
                 "tool_support": enum("restricted_monitor", "unsupported", "unverified"), "content_hash": HASH})
TRANSACTION = obj({"reset_epoch": I, "transaction_id": S, "trigger_cycle": I, "deadline_cycle": I,
                   "response_cycle": {"type": ["integer", "null"]}, "actual_response": {"type": ["integer", "null"]},
                   "expected_response": {"type": ["integer", "null"]},
                   "alignment": enum("matched", "missing_response", "extra_response", "unalignable", "cancelled", "not_applicable")})
SCHEMAS = {
    "CaseInput": versioned("CaseInput", {
        "case_id": enum("onehot", "fifo"), "bug_description": S, "top_module": S,
        "rtl": obj({"buggy": RTL, "fixed": RTL}), "existing_tests": array(S), "parameters": MAP,
        "clock": CLOCK, "reset": RESET, "signals": obj({"inputs": MAP, "outputs": MAP, "mapping": MAP}),
        "environment": array(SOURCE), "tool_config": TOOL, "input_hashes": {"type": "object", "additionalProperties": HASH},
        "obligation_source": S, "limitations": array(S)}),
    "Obligation": versioned("Obligation", {
        "obligation_id": S, "description": S, "scope": S, "parameters": MAP, "branches": array(S),
        "trigger": S, "response": S, "capture": S, "clock": CLOCK, "latency": obj({"min": I, "max": I}),
        "reset": RESET, "exceptions": array(S), "signals": MAP, "input_constraints": array(SOURCE),
        "sources": array(SOURCE), "confirmation": enum("imported_confirmed", "human_confirmed", "unconfirmed"),
        "initialization": S, "judge": obj({"reference": S, "version": S, "sha256": HASH})}),
    "Evidence": versioned("Evidence", {
        "evidence_id": HASH, "revision": I, "previous_revision_hash": {"type": ["string", "null"]},
        "revision_reason": S, "case_id": S, "obligation_ids": array(S), "branch": S,
        "sources": array(MAP), "rtl_version": enum("buggy", "fixed"), "input_hash": HASH,
        "config_hash": HASH, "behavior_hash": HASH, "label": enum("legal", "target_violation", "unknown"),
        "scope": S, "judge": MAP, "unknown_reason": {"type": ["string", "null"]}, "transaction": TRANSACTION,
        "artifacts": obj({"stimulus": S, "waveform": S, "trace": S, "log": S, "reproduce": S, "run": S})}),
    "AssertionSet": versioned("AssertionSet", {"set_id": S, "version": I, "case_id": S,
        "contract_hash": HASH, "environment_hash": HASH, "assertions": array(ASSERTION), "source": S}),
    "ReplayResult": versioned("ReplayResult", {"case_id": S, "snapshot_hash": HASH, "assertion_set_hash": HASH,
        "backend": S, "status": enum("complete", "incomplete"), "evaluations": array(MAP), "summary": MAP, "runs": array(S)}),
    "RefinementAttempt": versioned("RefinementAttempt", {"attempt_id": S, "case_id": S, "snapshot_hash": HASH,
        "old_set_hash": HASH, "proposal_hash": HASH, "source": S, "feedback": array(MAP),
        "old_replay": S, "proposal_replay": S, "diff": S, "accepted": B, "reasons": array(S)}),
    "Verdict": versioned("Verdict", {"case_id": S, "config_hash": HASH, "rtl_hashes": MAP, "assertion_hash": HASH,
        "evidence_hash": HASH, "versions": MAP, "stages": MAP, "search": MAP, "obligations": array(MAP),
        "replay": MAP, "refinement": MAP, "evidence_preservation": B, "flow_completed": B,
        "current_evidence_pass": B, "bounded_search": S, "native_sva": S, "formal_proof": S,
        "stop_reason": S, "limitations": array(S), "reproduce": S}),
}


def validate(kind, value):
    Draft202012Validator(SCHEMAS[kind]).validate(value)
    return value


def record(kind, **fields):
    return validate(kind, dict(schema_version=VERSION, kind=kind, **fields))


def export_schemas(folder):
    for kind, schema in SCHEMAS.items():
        write(Path(folder) / (kind + ".schema.json"), {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema})
