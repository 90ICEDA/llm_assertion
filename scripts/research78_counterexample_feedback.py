"""Continue the unchanged full-plan gate using actual research77 diagnostics.

No plan fields are merged, patched or substituted in the model execution path.
The existing research77 runner validates one whole response before any SVA call.
"""
import argparse
import copy
import json
from pathlib import Path
import research77_rule_consistency as gate
from research28_report import raw_response

ROOT,read,dump,b=gate.ROOT,gate.read,gate.dump,gate.b
P=ROOT/'deliverables/research77_prepare_20261024_r01'
R=ROOT/'deliverables/research77_real_20261024_r01'
A=ROOT/'deliverables/research77_audit_20261024_r01'


def feedback(plan,decision,rows):
    by_id={r['id']:r for r in rows}
    details={r['id']:r for r in decision['details']}
    examples=[]
    for ident in ('w0','w2','w5','w10'):
        row=by_id[ident];detail=details[ident]
        # Only actual public samples, actual returned labels and execution of
        # the model's own rule. No private corrected labels/answer table.
        examples.append(dict(id=ident,samples=row['public'],
            returned_window=detail['model_window'],
            evaluated_returned_rule=detail['executed_rule'],
            rule_agrees_with_returned_window=detail['rule_matches_window']))
    return dict(rejected_plan=plan,rejection_reasons=decision['reasons'],examples=examples,
        task='Return one complete revised plan, including all three rule objects and all11 windows, under the unchanged schema. Do not return a patch or only corrected fields. Every field will be checked together from this response; no previously correct field will be supplied by the evaluator.',
        diagnosis='Your cancellation rule selected check.rst=0, so executing your own rule cancels normal pending transitions and leaves the reset transition uncancelled. Review reset polarity in the supplied RTL/specification. Your w0 and w2 held-data labels also disagree with the selected anchor.mdata reference. Re-evaluate from the actual samples. Correcting cancellation alone or correcting only the window labels is insufficient. Keep the trigger condition distinct from the later hold requirement; decide reset cancellation first, then compare the selected reference with the checked data. Return the entire consistent plan.')


def prepare(out):
    gate.old.verify(P)
    assert read(A/'audit.json')['passed'] and read(R/'outcome.json')['model_calls']==1
    assert not read(R/'outcome.json')['plan_passed']
    rows=read(P/'windows.private.json');plan=read(R/'plan/v0/model_call/hold_plan.json')
    assert raw_response(R/'plan/v0/model_call',plan)
    decision=gate.validate(plan,rows);assert decision==read(R/'plan/v0/decision.json')
    assert not decision['accepted']
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):
        assert ok,name
        checks.append(name)
    f=feedback(plan,decision,rows)
    request=copy.deepcopy(read(P/'plan_request.preview.json'))
    body=json.loads(request['messages'][1]['content'])
    oldbody=copy.deepcopy(body)
    body.pop('previous_actual_rejection',None)
    body['actual_failed_plan_feedback']=f
    request['messages'][1]['content']=json.dumps(body)
    check('entire previous model response preserved',f['rejected_plan']==plan)
    check('exact actual rejection reasons',f['rejection_reasons']==decision['reasons'])
    check('schema unchanged',body['response_schema']==gate.schema(rows))
    check('same public samples',body['windows']==[r['public'] for r in rows])
    check('only failure feedback changed',
        {k:v for k,v in body.items() if k!='actual_failed_plan_feedback'}==
        {k:v for k,v in oldbody.items() if k!='previous_actual_rejection'})
    for example in f['examples']:
        check('actual rule execution '+example['id'],
            gate.evaluate(plan,example['samples'])==example['evaluated_returned_rule'])
        check('no private example fields '+example['id'],set(example)=={
            'id','samples','returned_window','evaluated_returned_rule','rule_agrees_with_returned_window'})
    # Local controls demonstrate simultaneous acceptance, not model success.
    def rejects(name,p):
        verdict=gate.validate(p,rows);check(name,not verdict['accepted'])
        try:gate.unlock(read(P/'sva_template.json'),p,dict(accepted=True),rows)
        except ValueError:locked=True
        else:locked=False
        check(name+' cannot unlock SVA',locked)
    rejects('actual unmodified failed response',plan)
    reset_only=copy.deepcopy(plan);reset_only['reset_cancellation']['rst']=1
    rejects('private fixture correcting cancellation only',reset_only)
    labels_only=copy.deepcopy(plan);labels_only['windows']=[r['expected'] for r in rows]
    rejects('private fixture correcting window labels only',labels_only)
    omitted=copy.deepcopy(plan);omitted['windows']=[]
    rejects('partial response never merged with old plan',omitted)
    good=dict(**gate.fixture_rules(),windows=[r['expected'] for r in rows])
    check('complete private positive fixture passes',gate.validate(good,rows)['accepted'])
    emitted=gate.unlock(read(P/'sva_template.json'),good,gate.validate(good,rows),rows)
    check('complete passed plan forwarded without substitution',
        json.loads(emitted['messages'][1]['content'])['verified_model_hold_plan']==good)
    check('runtime is the unchanged research77 runner',gate.run.__module__=='research77_rule_consistency')
    for n in ('windows.private.json','windows.public.json','window_cases.json','cases.json','history_cases.json',
              'initial.json','sva_template.json','excluded_inputs.json','protected.json','model_config.json'):
        dump(out/n,read(P/n));check('unchanged '+n,read(out/n)==read(P/n))
    dump(out/'plan_request.preview.json',request)
    dump(out/'feedback_checks.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,
        local_fixtures_never_sent=True,scope='Preparation and negative tests, not a passing real model plan.'))
    dump(out/'local_checks.json',gate.local_checks(rows,read(P/'sva_template.json')))
    bindings=read(P/'source_bindings.json')
    for p in (R/'plan/v0/model_call/hold_plan.json',R/'plan/v0/decision.json',R/'outcome.json',
              A/'audit.json',P/'native_reaudit.json',P/'sealed.json'):
        bindings[str(p)]=b.search.digest(p)
    dump(out/'source_bindings.json',bindings)
    dump(out/'native_reuse.json',dict(source=str(P/'native_reaudit.json'),sha256=b.search.digest(P/'native_reaudit.json'),
        raw_records=30,new_native_calls=0,scope='Previously audited native controls; no new native execution.'))
    protocol=copy.deepcopy(read(P/'protocol.json'))
    protocol.update(change='Actual research77 counterexample feedback only; unchanged schema, full-plan validator and native acceptance. One whole new model response, no historical field merging.',
        permission='Requires1 new plan call and explicit transfer of the remaining research77 conditional1 SVA slot. No remote calls in prepare.')
    dump(out/'protocol.json',protocol)
    dump(out/'code_versions.json',{str(p):b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.name:b.search.digest(p) for p in out.glob('*.json')})
    print('PREPARED',len(checks),'feedback checks',len(read(out/'local_checks.json')['checks']),'semantic checks',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--prepared',type=Path)
    p.add_argument('--authorization',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:gate.run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
