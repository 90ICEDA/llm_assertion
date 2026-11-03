"""Clean four-arm block after invalidating a debug-port feedback leak.

The original block, requests, outputs, pending call and source stay intact.
Only the development feedback projection and run namespace change. All four
arms restart from their identical frozen natural candidate.
"""
import argparse
import copy
import json
from pathlib import Path
import obligation_refinement_block as ref
import obligation_isolated_search as iso
from obligation_isolated_search import x

ORIGINAL_FEEDBACK=ref.public_feedback


def feedback(q,mode='both'):
    f=ORIGINAL_FEEDBACK(q,mode)
    d=x.read(x.OUT/'frozen'/q['case']/'definition.json')
    allowed={'cycle',d['rst'],*d['observation_base']}
    for event in f['witnesses']:
        event['recent_samples']=[{n:v for n,v in row.items() if n in allowed} for row in event['recent_samples']]
    assert all(set(row)<=allowed for event in f['witnesses'] for row in event['recent_samples'])
    return f


def query(k,arm,phase,i,rows,cs):
    ident=f'{k}/{arm}/{phase}/{i}'
    x.append(ref.BLOCK/'query_attempts.jsonl',dict(id=ident,input_sha256=x.digest(rows)))
    q=iso.evaluate(x.read(x.OUT/'frozen'/k/'definition.json'),rows,cs,'refinement_r03/'+ident)
    q.update(id=ident,case=k,arm=arm,phase=phase)
    x.append(ref.BLOCK/'queries.jsonl',q)
    return q


def init():
    old=x.OUT/'refinement_r02'
    results=[x.read(p) for p in old.glob('models/*/*/*/result.json')]
    attempts=list(old.glob('models/*/*/*/attempt.json'))
    x.dump(old/'INVALIDATED.json',dict(status='invalidated_no_method_comparison',
        reason='Public development recent_samples included second_new_sample_dbg despite public observation allowlist excluding it.',
        source_implementation=x.rel(x.OUT/'source_snapshot/scripts/obligation_refinement_block.py'),
        completed_model_calls=len(results),submitted_model_calls=len(attempts),
        interrupted_model_calls=len(attempts)-len(results),interrupted_tokens=None,
        known_prompt_tokens=sum(r.get('prompt_tokens') or 0 for r in results),
        known_completion_tokens=sum(r.get('completion_tokens') or 0 for r in results),
        all_artifacts_retained=True,stage1_stage2_affected=False))
    ref.init()
    p=x.read(ref.BLOCK/'protocol.json')
    p.update(block='refinement_r03',replaces_invalidated='refinement_r02',
             interface_fix='Recent development samples projected to public observation_base plus cycle/reset; all arms restarted, no debug ports, no hidden answers.',
             predecessor_cost=x.rel(old/'INVALIDATED.json'))
    x.dump(ref.BLOCK/'protocol.json',p)
    freeze=x.read(ref.BLOCK/'freeze.json')
    freeze[x.rel(ref.BLOCK/'protocol.json')]=x.sha(ref.BLOCK/'protocol.json')
    freeze[x.rel(Path(__file__))]=x.sha(Path(__file__))
    x.dump(ref.BLOCK/'freeze.json',freeze)
    x.snapshot(Path(__file__))
    # Exercise the interface against actual prior development data, not hidden.
    q=json.loads((old/'queries.jsonl').read_text().splitlines()[0])
    public=feedback(q)
    assert 'second_new_sample_dbg' not in json.dumps(public)
    x.dump(ref.BLOCK/'interface_qualification.json',dict(passed=True,source_query=q['id'],public_feedback=public))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('action',choices=['init','develop','heldout'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;ref.BLOCK=x.OUT/'refinement_r03'
    ref.public_feedback=feedback;ref.query=query
    if a.action=='init':init()
    else:getattr(ref,a.action)()
