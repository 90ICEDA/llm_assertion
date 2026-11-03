from __future__ import annotations

from pathlib import Path

import train_pilot_qwen3 as implementation

ROOT = Path(__file__).resolve().parents[1]
implementation.PILOT = ROOT / "outputs/behavioral_preference_pilot_v2"
implementation.DATA = implementation.PILOT / "training_corpora_v2"
implementation.FORMAL_TRAINING_DIR = "formal_training_v3"

if __name__ == "__main__":
    implementation.main()
