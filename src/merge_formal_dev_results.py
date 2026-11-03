from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


KEY = ("model_label", "case_id", "method", "candidate_index")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge formally evaluated dev results with provenance checks.")
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest-output")
    args = parser.parse_args()

    inputs = [Path(value).resolve() for value in args.input]
    output = Path(args.output).resolve()
    manifest_output = Path(args.manifest_output).resolve() if args.manifest_output else output.with_suffix(".manifest.json")
    rows: list[dict[str, str]] = []
    fieldnames: list[str] | None = None
    seen: set[tuple[str, ...]] = set()

    for path in inputs:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            current = list(reader.fieldnames or [])
            if fieldnames is None:
                fieldnames = current
            elif current != fieldnames:
                raise RuntimeError(f"CSV schema mismatch: {path}")
            for row in reader:
                key = tuple(row[name] for name in KEY)
                if key in seen:
                    raise RuntimeError(f"Duplicate candidate key: {key}")
                seen.add(key)
                rows.append(row)

    if not rows or fieldnames is None:
        raise RuntimeError("No result rows found")
    rows.sort(key=lambda row: tuple(row[name] for name in KEY))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter((row["model_label"], row["model_name"], row["representation_label"]) for row in rows)
    cases = {row["case_id"] for row in rows}
    payload = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": [{"path": str(path), "sha256": sha256(path)} for path in inputs],
        "output": str(output),
        "output_sha256": sha256(output),
        "row_count": len(rows),
        "case_count": len(cases),
        "counts": [
            {"model_label": key[0], "model_name": key[1], "representation": key[2], "rows": value}
            for key, value in sorted(counts.items())
        ],
        "duplicate_candidate_keys": 0,
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
