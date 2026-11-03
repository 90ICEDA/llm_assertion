import csv, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
import behavioral_preference_v3_gate as v3

with (ROOT/"outputs/behavioral_preference_pilot_v1/selected_train_parents.csv").open(encoding="utf-8-sig",newline="") as f:
    v3.GATE_IDS=[r["parent_bug_id"] for r in csv.DictReader(f)]
v3.OUT=ROOT/"outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30"

if len(sys.argv)!=2 or sys.argv[1] not in ("prepare","ingest"):
    raise SystemExit("usage: run_behavioral_preference_v3_pilot.py prepare|ingest")
v3.prepare() if sys.argv[1]=="prepare" else v3.ingest()
