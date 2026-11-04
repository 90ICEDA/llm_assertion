"""Read-only compact progress, safe to run while the campaign is active."""
import json
from pathlib import Path
from collections import Counter

root=Path(__file__).resolve().parents[1]/'deliverables/research199_refinement_execute_20261104_r01'
def read(path,default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
ledger=read(root/'ledger.json',[]); done=read(root/'progress.json',[])
rounds=[r for path in root.glob('*/*/*/refinement/rounds.json') for r in read(path,[])]
print(json.dumps(dict(reserved=len(ledger),frozen=len(done),transport=Counter(r['status'] for r in ledger),round_status=Counter(r.get('status','in_progress') for r in rounds),
    running=sorted({r['id'] for r in ledger}-{r['id'] for r in done}),
    recent=[{k:r.get(k) for k in ('id','accepted_rounds','regression_proposed','termination_reason')} for r in done[-3:]],
    active=[dict(id=r['id'],round=r['round']) for r in ledger if r['status']=='reserved_no_retry']),ensure_ascii=False))
