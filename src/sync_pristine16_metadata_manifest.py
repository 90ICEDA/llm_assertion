from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"rtl_cases_real_scale210_independent"
SEAL=ROOT/"outputs/pristine_trace_router_v1/sealed_test_manifest.json"
FIELDS=("spec","golden_sva","first_divergence","relevant_signals","temporal_type","status")

def main()->None:
    ids={x["case_id"] for x in json.loads(SEAL.read_text(encoding="utf-8"))["cases"]}
    for case_id in ids:
        meta_path=DATA/case_id/"case_metadata.json"
        meta=json.loads(meta_path.read_text(encoding="utf-8"))
        first=meta.get("first_divergence") or {}
        if "held_out" in first:
            first["heldout"]=first.pop("held_out")
            meta_path.write_text(json.dumps(meta,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    for filename in ("independent_new_bug_manifest.json","case_manifest.json"):
        path=DATA/filename
        if not path.exists(): continue
        payload=json.loads(path.read_text(encoding="utf-8")); changed=0
        for row in payload["cases"]:
            if row["name"] not in ids: continue
            meta=json.loads((DATA/row["name"]/"case_metadata.json").read_text(encoding="utf-8"))
            for field in FIELDS: row[field]=meta[field]
            changed+=1
        path.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"{filename}: synchronized {changed} sealed cases")

if __name__=="__main__": main()
