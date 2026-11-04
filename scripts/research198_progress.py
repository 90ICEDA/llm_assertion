"""Read-only campaign progress; tolerate JSON files being written."""
from collections import Counter
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'deliverables/research198_refinement_execute_20261104_r01'
def read(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):return default
ledger=read(root/'ledger.json',[]);progress=read(root/'progress.json',[]);rows=[]
for path in root.glob('*/*/*/refinement/rounds.json'):
    rows += [dict(id='/'.join(path.relative_to(root).parts[:3]),**r) for r in read(path,[])]
print(json.dumps(dict(reserved=len(ledger),frozen=len(progress),calls=dict(Counter(x['status'] for x in ledger)),
    statuses=dict(Counter(r.get('status','native_pending') for r in rows)),
    accepted_stages=dict(Counter(r.get('stage') for r in rows if r.get('status')=='accepted')),
    stages=dict(Counter(r.get('stage') for r in rows if r.get('stage'))),
    recent_frozen=[dict(id=r.get('registered_id'),reason=r.get('termination_reason'),error=r.get('error')) for r in progress[-3:]],
    complete=read(root/'outcome.json',None)),ensure_ascii=False))
