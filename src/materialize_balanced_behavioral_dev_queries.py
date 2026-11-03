from __future__ import annotations
import hashlib,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1"
OUT=BASE/"dev_top1_v1"; SPLIT=BASE/"parent_split_24_6.jsonl"; PROMPTS=ROOT/"outputs/behavioral_preference_pilot_v2/training_corpora_v2/prompts"
FORBIDDEN=("heldout","held-out","fp set","tp set","test outcome","target_detect","fixed_safe")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    manifest_path=OUT/"query_manifest.json"
    if manifest_path.exists(): raise RuntimeError("refusing to overwrite frozen dev manifest")
    split=[json.loads(x) for x in SPLIT.read_text().splitlines() if x.strip()]; dev=[x for x in split if x["split"]=="dev"]
    if len(dev)!=6: raise RuntimeError("expected exactly six frozen dev parents")
    records=[]
    for row in dev:
        source=PROMPTS/row["parent_bug_id"]/"prompt.txt"; prompt=source.read_text(encoding="utf-8")
        hits=[x for x in FORBIDDEN if x in prompt.lower()]
        if hits: raise RuntimeError(f"outcome leakage in {row['parent_bug_id']}: {hits}")
        match=re.search(r"antecedent_signal and consequent_signal must be one of:\s*(.+?)\.\s*$",prompt,re.M)
        if not match: raise RuntimeError(f"semantic signal list missing: {row['parent_bug_id']}")
        signals=[x.strip() for x in match.group(1).split(",")]
        directory=OUT/"queries"/row["parent_bug_id"]; directory.mkdir(parents=True,exist_ok=True); target=directory/"prompt.txt"
        target.write_text(prompt,encoding="utf-8",newline="\n")
        records.append({**row,"case_id":row["parent_bug_id"],"query_id":hashlib.sha256(("balanced_dev_top1_v1\0"+row["parent_bug_id"]).encode()).hexdigest()[:24],"prompt_path":str(target.relative_to(ROOT)).replace("\\","/"),"prompt_sha256":sha(target),"semantic_signals":signals})
    manifest={"status":"frozen_before_any_dev_generation","version":"balanced_behavioral_train_parent_dev_top1_v1","selection_scope":"six parents frozen before balanced training; no OOD queries or outcomes","query_count":6,"generation_count":18,"split_manifest_sha256":sha(SPLIT),"frozen_objective_sha256":sha(BASE/"balanced_behavioral_objective_v1_frozen.json"),"decode":{"temperature":0.0,"do_sample":False,"num_return_sequences":1,"max_new_tokens":128,"repair":False,"reranker":False,"selector":False,"heldout_information":False,"constraint":"strict canonical five-key JSON trie then EOS"},"records":sorted(records,key=lambda x:x["query_id"])}
    OUT.mkdir(parents=True,exist_ok=True); manifest_path.write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({"status":"pass","query_count":6,"generation_count":18,"manifest_sha256":sha(manifest_path),"dev_projects":sorted({x['source_project'] for x in dev}),"dev_bug_families":len({x['bug_family'] for x in dev})},sort_keys=True))
if __name__=="__main__": main()
