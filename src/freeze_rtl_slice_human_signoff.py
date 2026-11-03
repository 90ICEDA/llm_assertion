from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "outputs" / "rtl_context_slice_audit20"
SIGNOFF = AUDIT / "human_signoff"
SAMPLE = AUDIT / "sample.json"
CHECKLIST = SIGNOFF / "human_review_checklist.csv"
ATTESTATION = SIGNOFF / "human_reviewer_attestation.json"
FREEZE = SIGNOFF / "independent_human_signoff_freeze.json"
EXPECTED_SAMPLE_SHA256 = "846a62794192d30ce3483f6751bcdd2a8d2aa6c8569ddf1fc7aef606606233a7"
REQUIRED_TEXT = "I am a human reviewer and independently inspected all 20 fixed RTL slices; I did not resample the cases and I am not signing on behalf of an AI system."
CHECK_COLUMNS = [
    "no_leakage",
    "relevant_signals_declared",
    "relevant_logic_retained",
    "no_nonexistent_signals",
    "independent_parse_elaboration",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if sha256(SAMPLE) != EXPECTED_SAMPLE_SHA256:
        raise RuntimeError("Fixed sample hash changed; resampling is forbidden")
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    expected_cases = list(sample["cases"])
    with CHECKLIST.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    observed_cases = [row.get("case_id", "").strip() for row in rows]
    if observed_cases != expected_cases:
        raise RuntimeError("Checklist must contain the exact fixed 20 cases in locked order")
    failures = []
    for row in rows:
        case_id = row["case_id"]
        for column in CHECK_COLUMNS:
            if row.get(column, "").strip().upper() != "PASS":
                failures.append(f"{case_id}:{column} is not PASS")
        if not row.get("review_notes", "").strip():
            failures.append(f"{case_id}:review_notes is blank")
    if failures:
        raise RuntimeError("Human checklist is incomplete or contains failures:\n" + "\n".join(failures))

    attestation = json.loads(ATTESTATION.read_text(encoding="utf-8"))
    required_fields = [
        "reviewer_full_name", "reviewer_affiliation_or_role", "review_date",
        "reviewer_signature", "independence_attestation", "overall_verdict",
    ]
    missing = [field for field in required_fields if not str(attestation.get(field, "")).strip()]
    if missing:
        raise RuntimeError(f"Unsigned attestation; blank fields: {missing}")
    identity = " ".join(str(attestation.get(field, "")) for field in ("reviewer_full_name", "reviewer_signature")).lower()
    if any(marker in identity for marker in ("codex", "chatgpt", "openai", "claude", "ai assistant")):
        raise RuntimeError("Independent reviewer identity may not be an AI/Codex identity")
    if attestation["independence_attestation"].strip() != REQUIRED_TEXT:
        raise RuntimeError("Independence attestation must exactly match required_independence_text")
    if attestation["overall_verdict"].strip().upper() != "PASS":
        raise RuntimeError("Overall human verdict is not PASS")
    if int(attestation.get("fixed_sample_seed", -1)) != int(sample["seed"]):
        raise RuntimeError("Attested sample seed mismatch")
    if str(attestation.get("fixed_sample_sha256", "")).lower() != EXPECTED_SAMPLE_SHA256:
        raise RuntimeError("Attested sample hash mismatch")
    try:
        date.fromisoformat(attestation["review_date"].strip())
    except ValueError as exc:
        raise RuntimeError("review_date must be ISO YYYY-MM-DD") from exc

    evidence = {
        "schema_version": 1,
        "status": "frozen_independent_human_slice_review_pass",
        "sample_seed": sample["seed"],
        "sample_case_count": len(expected_cases),
        "sample_sha256": sha256(SAMPLE),
        "reviewer_full_name": attestation["reviewer_full_name"],
        "reviewer_affiliation_or_role": attestation["reviewer_affiliation_or_role"],
        "review_date": attestation["review_date"],
        "reviewer_signature": attestation["reviewer_signature"],
        "overall_verdict": "PASS",
        "resampled": False,
        "checklist_sha256": sha256(CHECKLIST),
        "attestation_sha256": sha256(ATTESTATION),
        "automatic_audit_sha256": sha256(AUDIT / "audit_v3" / "rtl_small_slice_audit.csv"),
        "iverilog_gate_sha256": sha256(AUDIT / "iverilog_gate" / "iverilog_slice_gate.csv"),
    }
    FREEZE.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
