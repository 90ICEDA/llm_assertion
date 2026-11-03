"""Valid four-arm pilot with a public allowlist and validator feedback loop.

Both earlier, invalidated pilot blocks remain immutable audit evidence.
"""
import argparse
import json
from pathlib import Path
import obligation_refinement_public as public
from obligation_refinement_public import ref, iso, x

ORIGINAL_CALL=ref.call_model


def call_model(k,arm,round_no,candidates,feedback):
    d=x.read(x.OUT/'frozen'/k/'definition.json')
    names=sorted(d['observation_base'])
    allowed=names+[f'p{i}_{n}' for i in (1,2,3) for n in names]
    interface=dict(kind='public_expression_contract',allowed_identifiers=allowed,
        allowed_function='popcount(declared_unsigned_signal)',
        reset='Reset is handled implicitly by the executor. Do NOT reference '+d['rst']+' in antecedent or consequent. It is trace metadata, not an allowed expression identifier.',
        history='Use the listed p1/p2/p3 identifiers. No $past, property text, custom disable iff, or debug/internal signals.')
    if round_no:
        previous=ref.BLOCK/'models'/k/arm/str(round_no-1)
        result=x.read(previous/'result.json')
        interface['previous_validation_status']=result['status']
        interface['previous_validation_error']=result.get('error')
        if result['status']!='parsed' and (previous/'response.raw.json').exists():
            interface['rejected_proposal_for_repair']=x.read(previous/'response.raw.json').get('message',{}).get('content')
    return ORIGINAL_CALL(k,arm,round_no,candidates,[interface,*feedback])


def query(k,arm,phase,i,rows,cs):
    ident=f'{k}/{arm}/{phase}/{i}'
    x.append(ref.BLOCK/'query_attempts.jsonl',dict(id=ident,input_sha256=x.digest(rows)))
    q=iso.evaluate(x.read(x.OUT/'frozen'/k/'definition.json'),rows,cs,'refinement_r04/'+ident)
    q.update(id=ident,case=k,arm=arm,phase=phase)
    x.append(ref.BLOCK/'queries.jsonl',q)
    return q


def init():
    old=x.OUT/'refinement_r03'
    results=[x.read(p) for p in old.glob('models/*/*/*/result.json')]
    attempts=list(old.glob('models/*/*/*/attempt.json'))
    x.dump(old/'INVALIDATED.json',dict(status='invalidated_common_feedback_loop_incomplete',
        reason='Validator failures were not returned to the next model iteration; public expression allowlist was not explicit enough about implicit reset. All arms restarted with these shared mechanisms fixed.',
        completed_model_calls=len(results),submitted_model_calls=len(attempts),interrupted_model_calls=len(attempts)-len(results),
        interrupted_tokens=None,known_prompt_tokens=sum(r.get('prompt_tokens') or 0 for r in results),
        known_completion_tokens=sum(r.get('completion_tokens') or 0 for r in results),artifacts_retained=True))
    ref.init()
    p=x.read(ref.BLOCK/'protocol.json');p.update(block='refinement_r04',replaces_invalidated=['refinement_r02','refinement_r03'],
        common_interface_fix='Public trace field projection, explicit expression identifier allowlist, implicit reset rule, previous validator error and rejected proposal returned identically in every arm.',
        model_unchanged=True,no_manual_repairs=True)
    x.dump(ref.BLOCK/'protocol.json',p)
    freeze=x.read(ref.BLOCK/'freeze.json');freeze[x.rel(ref.BLOCK/'protocol.json')]=x.sha(ref.BLOCK/'protocol.json')
    for f in (Path(__file__),Path(public.__file__)):freeze[x.rel(f)]=x.sha(f)
    x.dump(ref.BLOCK/'freeze.json',freeze);x.snapshot(Path(__file__))
    q=json.loads((old/'queries.jsonl').read_text().splitlines()[0]);projected=public.feedback(q)
    assert 'second_new_sample_dbg' not in json.dumps(projected)
    x.dump(ref.BLOCK/'interface_qualification.json',dict(passed=True,source_query=q['id'],public_feedback=projected,
        validation_errors_visible=True,allowed_identifiers_explicit=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('action',choices=['init','develop','heldout'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;ref.BLOCK=x.OUT/'refinement_r04'
    ref.public_feedback=public.feedback;ref.query=query;ref.call_model=call_model
    if a.action=='init':init()
    else:getattr(ref,a.action)()
