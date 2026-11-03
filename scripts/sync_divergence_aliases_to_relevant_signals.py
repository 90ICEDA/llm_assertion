from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "rtl_cases_real_scale210_independent"


def main() -> None:
    changed = []
    for metadata_path in sorted(DATASET.glob("case4*/case_metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        relevant = list(metadata.get("relevant_signals", []))
        seen = set(relevant)
        for divergence in metadata.get("first_divergence", {}).values():
            if not isinstance(divergence, dict):
                continue
            for signal in divergence.get("signals", []):
                if signal not in seen:
                    relevant.append(signal)
                    seen.add(signal)
        if relevant != metadata.get("relevant_signals", []):
            metadata["relevant_signals"] = relevant
            metadata_path.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            changed.append(metadata_path.parent.name)
    print(json.dumps({"changed_count": len(changed), "changed_cases": changed}, indent=2))


if __name__ == "__main__":
    main()
