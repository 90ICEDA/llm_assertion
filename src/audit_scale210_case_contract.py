from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "rtl_cases_real_scale210_independent"
REQUIRED_FIELDS = (
    "parent_bug_id", "source_project", "source_module", "source_commit",
    "bug_class", "bug_family", "spec", "golden_sva", "first_divergence",
    "relevant_signals", "temporal_type",
)
REQUIRED_FILES = (
    "correct.v", "buggy.v", "rtl_mutation.diff", "spec.md", "golden.sva",
    "waveform_good.csv", "waveform_bad.csv", "waveform_good_holdout.csv",
    "waveform_bad_holdout.csv", "waveform_good_decoy.csv", "waveform_bad_decoy.csv",
)
VARIANTS = (("primary", ""), ("heldout", "_holdout"), ("decoy", "_decoy"))
LEAK_RE = re.compile(r"mutation|buggy line|source line|original rtl|assertionforge_mutation", re.I)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def first_divergence(good_path: Path, bad_path: Path) -> dict[str, object] | None:
    good, bad = read_rows(good_path), read_rows(bad_path)
    for index, (g, b) in enumerate(zip(good, bad)):
        signals = sorted(k for k in set(g) & set(b) if k != "time_ps" and g[k] != b[k])
        if signals:
            return {
                "time_ps": int(g.get("time_ps", index)), "sample_index": index,
                "signals": signals,
                "good_values": {k: g[k] for k in signals},
                "bad_values": {k: b[k] for k in signals},
            }
    return None


def assertion_text(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("assertion") or value.get("sva") or "")
    return str(value or "")


def main() -> None:
    rows = []
    for case_dir in sorted(DATASET.glob("case4*")):
        errors: list[str] = []
        meta_path = case_dir / "case_metadata.json"
        if not meta_path.is_file():
            rows.append({"case_id": case_dir.name, "complete": False, "errors": "missing case_metadata.json"})
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for field in REQUIRED_FIELDS:
            value = meta.get(field)
            if value in (None, "", [], {}): errors.append(f"missing field:{field}")
        for name in REQUIRED_FILES:
            path = case_dir / name
            if not path.is_file() or path.stat().st_size == 0: errors.append(f"missing/empty file:{name}")
        if meta.get("parent_bug_id") != case_dir.name: errors.append("parent_bug_id is not unique case id")
        spec = str(meta.get("spec", ""))
        if LEAK_RE.search(spec): errors.append("spec contains mutation/implementation leakage wording")
        sva = assertion_text(meta.get("golden_sva"))
        if not sva.startswith("assert property"): errors.append("golden SVA is not an assert property")
        relevant = {re.sub(r"\[[^]]+\]$", "", str(x)) for x in meta.get("relevant_signals", [])}
        recorded = meta.get("first_divergence", {}) if isinstance(meta.get("first_divergence"), dict) else {}
        trace_hashes = []
        for label, suffix in VARIANTS:
            good, bad = case_dir / f"waveform_good{suffix}.csv", case_dir / f"waveform_bad{suffix}.csv"
            if not good.is_file() or not bad.is_file(): continue
            trace_hashes.append((sha(good), sha(bad)))
            actual = first_divergence(good, bad)
            if actual is None:
                errors.append(f"{label}:no good/bad divergence")
                continue
            rec = recorded.get(label, {}) if isinstance(recorded.get(label), dict) else {}
            if rec.get("time_ps") != actual["time_ps"]: errors.append(f"{label}:first_divergence time mismatch")
            bases = {re.sub(r"\[[^]]+\]$", "", s) for s in actual["signals"]}
            if not bases & relevant: errors.append(f"{label}:divergence signals absent from relevant_signals")
        if len(set(trace_hashes)) != 3: errors.append("primary/heldout/decoy trace pairs are not distinct")
        if (case_dir / "correct.v").is_file() and (case_dir / "buggy.v").is_file() and sha(case_dir / "correct.v") == sha(case_dir / "buggy.v"):
            errors.append("correct and buggy RTL identical")
        rows.append({
            "case_id": case_dir.name, "source_project": meta.get("source_project", ""),
            "bug_class": meta.get("bug_class", ""), "complete": not errors,
            "error_count": len(errors), "errors": ";".join(errors),
        })

    audit = DATASET / "complete_case_contract_audit.csv"
    with audit.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary = {
        "schema_version": 2, "case_count": len(rows),
        "complete_case_count": sum(bool(x["complete"]) for x in rows),
        "incomplete_case_count": sum(not bool(x["complete"]) for x in rows),
        "all_complete": all(bool(x["complete"]) for x in rows),
        "required_fields": list(REQUIRED_FIELDS), "required_files": list(REQUIRED_FILES),
        "checks": ["unique parent", "behavioral spec leakage wording", "golden assert property", "three real divergences", "first-divergence match", "relevant signal coverage", "distinct trace variants", "distinct RTL"],
    }
    out = DATASET / "complete_case_contract_summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    raise SystemExit(0 if summary["all_complete"] else 1)


if __name__ == "__main__":
    main()
