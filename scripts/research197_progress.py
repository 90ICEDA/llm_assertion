"""Read-only compact progress, tolerant of a JSON write in flight."""
from collections import Counter
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]/'deliverables/research197_refinement_execute_20261104_r01'
def read(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):return default
ledger=read(root/'ledger.json',[]);progress=read(root/'progress.json',[]);rounds=[]
for path in root.glob('*/*/*/refinement/rounds.json'):
    for row in read(path,[]):rounds.append(dict(trajectory='/'.join(path.relative_to(root).parts[:3]),**row))
print(json.dumps(dict(reserved=len(ledger),call_statuses=dict(Counter(r['status'] for r in ledger)),frozen=len(progress),
    round_statuses=dict(Counter(r.get('status','in_progress') for r in rounds)),
    native_in_progress=[r['trajectory'] for r in rounds if 'status' not in r],
    accepted_count=sum(r.get('status')=='accepted' for r in rounds),
    accepted_stages=dict(Counter(r.get('stage') for r in rounds if r.get('status')=='accepted')),
    executed_stages=dict(Counter(r.get('stage') for r in rounds if r.get('stage'))),
    recent_accepted=[dict(id=r['trajectory'],round=r['round'],stage=r.get('stage')) for r in rounds if r.get('status')=='accepted'][-4:],
    recent_frozen=[dict(id=r['registered_id'],reason=r.get('termination_reason')) for r in progress[-3:]],
    completed=read(root/'outcome.json',None)),ensure_ascii=False))
