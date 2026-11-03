from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "rtl_cases_real_scale210_independent"
SEAL = ROOT / "outputs/pristine_trace_router_v1/sealed_test_manifest.json"
NAMES = ("tb.v", "tb_holdout.v", "tb_decoy.v")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expanded_text(path: Path, seen: set[Path] | None = None) -> str:
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen: return ""
    seen.add(path)
    text = path.read_text(encoding="utf-8")
    chunks = [text]
    for include in re.findall(r'`include\s+"([^"]+)"', text):
        candidate = path.parent / include
        if candidate.is_file(): chunks.append(expanded_text(candidate, seen))
    return "\n".join(chunks)


def main() -> None:
    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    failures: list[str] = []
    rows = []
    for item in seal["cases"]:
        case_id = item["case_id"]
        directory = DATA / case_id
        metadata = json.loads((directory / "case_metadata.json").read_text(encoding="utf-8"))
        module = metadata["source_module"]
        texts, hashes = [], []
        for name in NAMES:
            path = directory / name
            if not path.is_file() or path.stat().st_size == 0:
                failures.append(f"{case_id}: missing {name}")
                continue
            text = expanded_text(path)
            texts.append(text); hashes.append(digest(path))
            if not re.search(rf"\b{re.escape(module)}\s*(?:#\s*\(|[A-Za-z_]\w*\s*\()", text):
                failures.append(f"{case_id}/{name}: does not instantiate {module}")
            if "$dumpvars" not in text or "VCD" not in text:
                failures.append(f"{case_id}/{name}: missing +VCD/dumpvars trace hook")
        if len(set(hashes)) != 3:
            failures.append(f"{case_id}: primary/holdout/decoy are not three distinct files")
        for filename, key in (("correct.v", "correct_rtl_sha256"), ("buggy.v", "buggy_rtl_sha256"), ("rtl_mutation.diff", "mutation_diff_sha256")):
            if digest(directory / filename) != item[key]: failures.append(f"{case_id}: sealed {filename} changed")
        rows.append({"case_id": case_id, "module": module, "tb_count": len(hashes), "distinct_tb_count": len(set(hashes))})
    report = {"case_count": len(rows), "expected_tb_count": len(rows)*3, "failures": failures, "cases": rows, "passed": not failures}
    output = ROOT / "outputs/pristine_trace_router_v1/testbench_static_audit.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"case_count": len(rows), "failure_count": len(failures), "passed": not failures}, indent=2))
    if failures:
        for failure in failures: print("FAIL", failure)
        raise SystemExit(1)


if __name__ == "__main__": main()
