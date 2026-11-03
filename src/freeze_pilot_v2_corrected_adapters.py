from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/behavioral_preference_pilot_v2/formal_training_v3"
METHODS = ("ordinary_sft", "pass_count_dpo", "scalar_score_dpo", "random_probe_dominance_dpo", "full_disagreement_dominance_dpo")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    records = {}
    lines = []
    for method in METHODS:
        result = json.loads((BASE / method / "training_result.json").read_text(encoding="utf-8"))
        if result["status"] != "pass" or not result.get("response_eos_required"):
            raise RuntimeError(f"corrected training is not complete: {method}")
        checkpoint = (BASE / method / "latest_checkpoint.txt").read_text(encoding="utf-8").strip()
        adapter = BASE / method / checkpoint / "adapter_model.safetensors"
        digest = sha(adapter)
        relative = str(adapter.relative_to(ROOT)).replace("\\", "/")
        lines.append(f"{digest}  {relative}\n")
        records[method] = {"checkpoint": checkpoint, "adapter_path": str(adapter.parent.relative_to(ROOT)).replace("\\", "/"), "adapter_sha256": digest}
    hash_file = BASE / "final_adapter_hashes.sha256"
    hash_file.write_text("".join(lines), encoding="utf-8")
    manifest = {"status": "frozen_before_ast_smoke_v2", "methods": records, "hash_file_sha256": sha(hash_file)}
    (BASE / "final_adapter_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
