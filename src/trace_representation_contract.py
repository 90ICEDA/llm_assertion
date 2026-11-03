from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any


TRACE_REPRESENTATIONS = (
    "raw_trace",
    "naive_summary",
    "event_abstraction",
    "temporal_relation_abstraction",
)

METHOD_TO_REPRESENTATION = {
    "spec_rtl_raw_trace": "raw_trace",
    "spec_rtl_naive_summary": "naive_summary",
    "spec_rtl_event_abstraction": "event_abstraction",
    "spec_rtl_temporal_relation_abstraction": "temporal_relation_abstraction",
}

TEMPORAL_FIELDS = (
    "Trigger",
    "Polarity",
    "Ordering",
    "Observed delay",
    "Duration",
    "Reset",
    "Good/bad divergence",
    "Generalization boundary",
)


def normalized_nonempty_lines(text: str) -> set[str]:
    return {
        re.sub(r"\s+", " ", line).strip().lower()
        for line in str(text or "").splitlines()
        if re.sub(r"\s+", " ", line).strip()
    }


def mutation_added_lines(correct_rtl: str, buggy_rtl: str) -> set[str]:
    added: set[str] = set()
    for line in difflib.ndiff(correct_rtl.splitlines(), buggy_rtl.splitlines()):
        if line.startswith("+ "):
            normalized = re.sub(r"\s+", " ", line[2:]).strip().lower()
            if normalized and normalized not in {"begin", "end", "endcase"}:
                added.add(normalized)
    return added


def validate_temporal_relation_abstraction(
    text: str,
    *,
    golden_sva: str = "",
    expected_behavior: str = "",
    correct_rtl: str = "",
    buggy_rtl: str = "",
) -> list[str]:
    value = str(text or "").strip()
    errors: list[str] = []
    if not value.startswith("Temporal-relation abstraction:"):
        errors.append("wrong_header")

    field_values: dict[str, str] = {}
    bullet_lines = [line for line in value.splitlines() if line.startswith("- ")]
    if len(bullet_lines) != len(TEMPORAL_FIELDS):
        errors.append(f"wrong_field_count:{len(bullet_lines)}")
    for field in TEMPORAL_FIELDS:
        match = re.search(rf"(?mi)^- {re.escape(field)}:\s*(.+)$", value)
        if not match:
            errors.append(f"missing_field:{field}")
        else:
            field_values[field] = match.group(1).strip()
    allowed_prefixes = tuple(f"- {field}:" for field in TEMPORAL_FIELDS)
    if any(not line.startswith(allowed_prefixes) for line in bullet_lines):
        errors.append("unknown_field")

    low = value.lower()
    for label, forbidden in (("golden_sva", golden_sva), ("expected_behavior", expected_behavior)):
        needle = re.sub(r"\s+", " ", str(forbidden or "")).strip().lower()
        if needle and len(needle) >= 12 and needle in re.sub(r"\s+", " ", low):
            errors.append(f"leak:{label}")

    if any(token in low for token in ("golden sva", "golden assertion", "mutation diff", "buggy line", "mutation line")):
        errors.append("leak:marker")

    if correct_rtl and buggy_rtl:
        summary_lines = normalized_nonempty_lines(value)
        if summary_lines & mutation_added_lines(correct_rtl, buggy_rtl):
            errors.append("leak:mutation_added_line")

    delay = field_values.get("Observed delay", "").lower()
    if delay and not any(word in delay for word in ("observed", "trace", "unknown", "not identifiable")):
        errors.append("delay_not_scoped_to_observation")
    boundary = field_values.get("Generalization boundary", "").lower()
    if boundary and not (
        any(word in boundary for word in ("do not", "must not", "not infer", "not general"))
        and any(word in boundary for word in ("cycle", "literal", "constant", "value"))
    ):
        errors.append("missing_anti_overfit_boundary")

    # Exact cycle indices may document an observation only in the two evidence fields.
    for line in value.splitlines():
        if re.search(r"\b(?:cycle|t)\s*[=#:]?\s*\d+\b", line, re.I):
            if not line.startswith("- Observed delay:") and not line.startswith("- Good/bad divergence:"):
                errors.append("fixed_cycle_outside_observation")
                break
    return sorted(set(errors))


def case_contract_inputs(case_dir: Path, case_meta: dict[str, Any]) -> dict[str, str]:
    golden = case_meta.get("golden_sva") or {}
    if isinstance(golden, str):
        golden_text = golden
        expected_behavior = ""
    else:
        golden_text = golden.get("sva") or golden.get("assertion") or ""
        expected_behavior = golden.get("expected_behavior", "")
    return {
        "golden_sva": str(golden_text),
        "expected_behavior": str(expected_behavior),
        "correct_rtl": (case_dir / "correct.v").read_text(encoding="utf-8") if (case_dir / "correct.v").exists() else "",
        "buggy_rtl": (case_dir / "buggy.v").read_text(encoding="utf-8") if (case_dir / "buggy.v").exists() else "",
    }
