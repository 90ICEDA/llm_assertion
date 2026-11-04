"""Small read-only campaign snapshot; no credentials, payloads or test inputs."""
import argparse
from collections import Counter
import json
from pathlib import Path


def read(p,default):
    try:return json.loads(p.read_text(encoding='utf-8'))
    except FileNotFoundError:return default


def snapshot(root):
    root=Path(root);ledger=read(root/'ledger.json',[]);outcomes=read(root/'progress.json',[])
    frozen={r['registered_id'] for r in outcomes};rounds=[];tokens=0;unknown=0;paid=0
    for p in root.glob('*/*/*/refinement/rounds.json'):rounds+=read(p,[])
    for p in root.glob('*/*/*/refinement/round*/model_call/result.json'):
        r=read(p,{});paid+=r.get('model_calls',0)
        unknown+=int(r.get('prompt_tokens') is None or r.get('completion_tokens') is None)
        tokens+=(r.get('prompt_tokens') or 0)+(r.get('completion_tokens') or 0)
    return dict(frozen=len(outcomes),registered=64,reserved_calls=len(ledger),actual_model_calls=paid,
        call_status=dict(Counter(r['status'] for r in ledger)),known_tokens=tokens,unknown_usage_calls=unknown,
        round_status=dict(Counter(r.get('status','pending_native') for r in rounds)),
        active_called_trajectories=sorted({r['id'] for r in ledger}-frozen),
        outcome=read(root/'outcome.json',None))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();print(json.dumps(snapshot(a.root),ensure_ascii=False))
