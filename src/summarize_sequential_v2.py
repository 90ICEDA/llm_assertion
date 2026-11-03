from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/behavioral_preference_pilot_v1"
GEN = OUT / "sequential_generation_v2"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


accepted = json.loads((GEN / "accepted_index.json").read_text(encoding="utf-8"))
missing = json.loads((GEN / "missing_slots.json").read_text(encoding="utf-8"))
audit = [json.loads(line) for line in (GEN / "ingestion_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
request_index = json.loads((GEN / "request_index.json").read_text(encoding="utf-8"))

records = accepted["records"]
by_parent = Counter(r["parent_bug_id"] for r in records)
selected_parents = []
with (OUT / "selected_train_parents.csv").open(encoding="utf-8-sig") as f:
    import csv
    selected_parents = [row["parent_bug_id"] for row in csv.DictReader(f)]
attempt_calls = Counter()
for request in request_index["records"]:
    response = ROOT / Path(request["request_path"]).parent / "raw_response.json"
    if response.exists():
        attempt_calls[str(request["attempt"])] += 1

summary = {
    "protocol_version": "sequential_structured_v2_visible_compile_gate",
    "status": "attempts_1_through_4_exhausted_no_fabricated_candidates",
    "target_slots": accepted["target_count"],
    "accepted_compile_legal": accepted["accepted_count"],
    "remaining_slot_exhausted": missing["missing_count"],
    "target_pass": accepted["pass"],
    "attempt_response_counts": dict(sorted(attempt_calls.items())),
    "metrics_on_accepted": {
        "compile_ok": sum(bool(r["evaluation"].get("compile_ok")) for r in records),
        "fixed_safe": sum(bool(r["evaluation"].get("correct_pass")) for r in records),
        "target_detect": sum(bool(r["evaluation"].get("buggy_fail")) for r in records),
        "non_vacuous": sum(bool(r["evaluation"].get("non_vacuous")) for r in records),
    },
    "accepted_per_parent": {parent: by_parent[parent] for parent in selected_parents},
    "parents_with_8": sum(by_parent[parent] == 8 for parent in selected_parents),
    "parents_with_0": sum(by_parent[parent] == 0 for parent in selected_parents),
    "rejection_reason_counts": dict(sorted(Counter(r.get("reason", "unknown") for r in audit if not r.get("accepted")).items())),
    "hashes": {
        "frozen_protocol_sha256": sha256(OUT / "sequential_protocol_v2_frozen.json"),
        "request_index_sha256": sha256(GEN / "request_index.json"),
        "accepted_index_sha256": sha256(GEN / "accepted_index.json"),
        "ingestion_audit_sha256": sha256(GEN / "ingestion_audit.jsonl"),
        "missing_slots_sha256": sha256(GEN / "missing_slots.json"),
    },
}

target = OUT / "sequential_v2_final_supplement_audit.json"
target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
