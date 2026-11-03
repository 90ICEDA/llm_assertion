from __future__ import annotations
import train_pilot_qwen3 as implementation
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
implementation.PILOT=ROOT/"outputs/behavioral_preference_pilot_v2"
implementation.DATA=implementation.PILOT/"training_corpora_v1"
if __name__=="__main__":implementation.main()
