#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMAINING = ROOT / "deliverables/final46_mechanism_analysis_20260808/remaining78_review.jsonl"
ANNOTATIONS = ROOT / "analysis/final46_manual_failure_annotations.json"

# Explicit reviewer decisions, indexed against remaining78_review.jsonl.  These
# are not inferred by the analyzer; each tuple was assigned after comparing the
# golden relation with all four raw and four temporal candidate outcomes.
DECISIONS = {
    0:("delay","compile_form"),1:("delay","too_strong"),2:("trigger","vacuity"),
    3:("trigger","vacuity"),4:("trigger","vacuity"),5:("context_noise","too_strong"),
    6:("trigger","vacuity"),7:("duration","compile_form"),8:("delay","compile_form"),
    9:("trigger","vacuity"),10:("trigger","vacuity"),11:("duration","vacuity"),
    12:("delay","compile_form"),13:("hardcoding","too_weak"),14:("delay","compile_form"),
    15:("trigger","vacuity"),16:("trigger","vacuity"),17:("delay","too_weak"),
    18:("delay","too_weak"),19:("delay","vacuity"),20:("delay","too_weak"),
    21:("trigger","vacuity"),22:("polarity","compile_form"),23:("trigger","vacuity"),
    24:("delay","too_weak"),25:("delay","too_weak"),26:("trigger","vacuity"),
    27:("delay","compile_form"),28:("trigger","vacuity"),29:("delay","vacuity"),
    30:("trigger","vacuity"),31:("trigger","vacuity"),32:("trigger","vacuity"),
    33:("duration","too_strong"),34:("delay","compile_form"),35:("delay","too_strong"),
    36:("duration","compile_form"),37:("delay","too_weak"),38:("delay","compile_form"),
    39:("delay","too_weak"),40:("trigger","vacuity"),41:("trigger","vacuity"),
    42:("delay","compile_form"),43:("delay","too_weak"),44:("delay","compile_form"),
    45:("trigger","vacuity"),46:("polarity","compile_form"),47:("trigger","vacuity"),
    48:("delay","compile_form"),49:("delay","compile_form"),50:("trigger","vacuity"),
    51:("trigger","vacuity"),52:("delay","too_weak"),53:("delay","too_strong"),
    54:("delay","too_strong"),55:("duration","compile_form"),56:("delay","compile_form"),
    57:("hardcoding","too_weak"),58:("delay","too_strong"),59:("duration","too_strong"),
    60:("delay","too_weak"),61:("delay","too_strong"),62:("hardcoding","vacuity"),
    63:("delay","too_weak"),64:("trigger","vacuity"),65:("polarity","too_strong"),
    66:("delay","compile_form"),67:("delay","compile_form"),68:("delay","compile_form"),
    69:("delay","too_weak"),70:("delay","too_strong"),71:("delay","compile_form"),
    72:("delay","compile_form"),73:("delay","compile_form"),74:("delay","compile_form"),
    75:("trigger","vacuity"),76:("delay","compile_form"),77:("delay","too_weak"),
}


def modes(digest: str) -> str:
    return "/".join(re.findall(r"c\d+\[([^\]]+)\]", str(digest)))


def compact_golden(text: str) -> str:
    assertion = " ".join(str(text).split())
    assertion = re.sub(r"^// Pending semantic validation; not admitted\.\s*", "", assertion)
    return assertion[:420]


def evidence_for(row: dict, primary: str, secondary: str) -> str:
    golden = compact_golden(row.get("golden_sva", ""))
    raw_modes = modes(row.get("raw_candidate_digest", ""))
    temporal_modes = modes(row.get("temporal_candidate_digest", ""))
    controls = str(row.get("control_successes") or "none")
    explanation = {
        "delay": "The reviewed candidates do not preserve the golden same/next/exact-cycle relation; same-cycle collapse or unusable delayed syntax explains the observed failure modes.",
        "trigger": "The reviewed antecedents differ from the golden triggering event or do not occur in evaluation, producing vacuity/ineffectiveness despite a relevant consequent.",
        "polarity": "The reviewed trigger/value direction is reversed or attached to the wrong edge, so the property cannot observe the golden event.",
        "duration": "The reviewed candidates do not preserve the required hold/pulse length, or express it with an unsupported repetition/sequence form.",
        "context_noise": "The candidates select visible handshake proxies instead of the internal state transition in the golden property; successful alternate controls show that context selection changes the result.",
        "hardcoding": "The candidates specialize to witnessed literals, lanes, or selector combinations rather than the general relation in the golden property.",
    }[primary]
    return (
        f"Golden target: {golden} Raw c1-c4 outcomes: {raw_modes}; temporal c1-c4 outcomes: "
        f"{temporal_modes}. {explanation} Secondary code: {secondary}. Successful controls: {controls}."
    )


def main() -> None:
    remaining = [json.loads(line) for line in REMAINING.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(remaining) != 78 or set(DECISIONS) != set(range(78)):
        raise SystemExit("manual-review index mismatch")
    existing = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    existing_keys = {(x["model"], x["case_id"]) for x in existing}
    added = []
    for index, row in enumerate(remaining):
        key = (row["model"], row["case_id"])
        if key in existing_keys:
            raise SystemExit(f"duplicate manual annotation key: {key}")
        primary, secondary = DECISIONS[index]
        added.append({
            "model": row["model"],
            "case_id": row["case_id"],
            "quadrant": row["quadrant"],
            "primary": primary,
            "secondary": secondary,
            "evidence": evidence_for(row, primary, secondary),
        })
    combined = existing + added
    if len(combined) != 97 or len({(x["model"], x["case_id"]) for x in combined}) != 97:
        raise SystemExit("combined manual-review completeness failure")
    ANNOTATIONS.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"existing": len(existing), "added": len(added), "total": len(combined)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
