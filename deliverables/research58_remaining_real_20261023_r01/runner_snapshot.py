"""Spend only research58's remaining call after local feedback-size failure.

No retry of the first response and no extra call grant. Separate sealed compact
request and original interrupted run are retained. Native gates are unchanged.
"""
import argparse
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import research58_preservation_refinement as g

FIRST=g.ROOT/'deliverables/research58_real_20261023_r01'


def prepare(prep,out):
    out.mkdir(parents=True,exist_ok=False)
    assert g.read(FIRST/'outcome.json')['calls']==1 and not (FIRST/'v1').exists()
    native=g.read(FIRST/'v0/alignment/result.json');gate=g.read(FIRST/'v0/alignment/alignment_gate.json')
    candidate=g.read(FIRST/'v0/model_call/candidate.json')
    assert not gate['accepted']
    g.diagnostic.audit_native(FIRST/'v0/alignment',candidate,prep,'alignment')
    info=g.old.acceptance.inspect(native['ledger']);representatives={}
    for r in native['ledger']:
        if r['evidence_id'] in info['misses']:
            representatives.setdefault((r['sample']['instruction']>>12)&7,g.prior.row_view(r))
    feedback=dict(actual_model_proposal=g.read(FIRST/'v0/model_call/model_edit.json'),
        counts=native['counts'],required_untriggered=gate['required_untriggered'],
        verdict='Rejected by actual native development alignment; all exposed targets must trigger and be detected.',
        miss_representatives=list(representatives.values())[:2],
        total_distinct_funct3_miss_groups=len(representatives),complete_diagnosis_retained_locally=True)
    req=g.payload(prep,g.read(prep/'shared_initial.json'),feedback)
    size=sum(len(m['content'].encode()) for m in req['messages'])
    assert size<=g.prior.MAX_MESSAGE_BYTES,size
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=g.Model(out/'transport_metadata',prep)
        assert model._payload(g.read(prep/'shared_initial.json'),None,feedback,'sva')==req and not model.calls
    g.dump(out/'feedback.json',feedback);g.dump(out/'request.preview.json',req)
    sources=[prep/'sealed.json',FIRST/'outcome.json',FIRST/'v0/model_call/candidate.json',FIRST/'v0/model_call/model_edit.json',FIRST/'v0/alignment/result.json',FIRST/'v0/alignment/alignment_gate.json',FIRST/'authorization.json',Path(__file__)]
    g.dump(out/'sources.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in sources})
    g.dump(out/'protocol.json',dict(scope='research58_same_grant_remaining_call',first_calls=1,remaining_calls=1,total_authorized_calls=2,retries=0,
        request_sha256=g.old.digest(out/'request.preview.json'),message_bytes=size,
        change='Deduplicated latest diagnostic view only, same model, inputs, purpose and acceptance. Original size failure retained.',
        model_calls=0,independent_test='not_run'))
    g.dump(out/'sealed.json',{p.relative_to(out).as_posix():g.old.digest(p) for p in out.rglob('*.json')})
    print('CONTINUATION_PREPARED',size,'bytes; real_calls0',flush=True)


def run(prep,sealed,out):
    assert g.read(FIRST/'outcome.json')['calls']==1 and not (FIRST/'v1').exists()
    auth=g.read(FIRST/'authorization.json');assert auth['authorized_calls']==2 and auth['scope']=='research58_preservation_refinement'
    for n,h in g.read(prep/'sealed.json').items():assert g.old.digest(prep/n)==h,n
    for n,h in g.read(prep/'source_hashes.json').items():assert g.old.digest(g.ROOT/'scripts'/n)==h,n
    for n,h in g.read(sealed/'sealed.json').items():assert g.old.digest(sealed/n)==h,n
    for n,h in g.read(sealed/'sources.json').items():assert g.old.digest(g.ROOT/n)==h,n
    # This continuation has one canonical output. Existing output prevents reuse
    # of the remaining-call grant, including after a transport failure.
    assert out==g.ROOT/'deliverables/research58_remaining_real_20261023_r01'
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(FIRST/'authorization.json',out/'original_authorization.json')
    shutil.copy2(sealed/'protocol.json',out/'protocol.json')
    shutil.copy2(Path(__file__),out/'runner_snapshot.py')
    current=g.read(prep/'shared_initial.json');baseline=g.read(prep/'baseline_full.json')
    model=g.Model(out,prep);model.config['max_model_calls']=1
    model.known.append(dict(source=str(FIRST/'v0/model_call/candidate.json'),signature=g.prior.previous.op_signature(g.read(FIRST/'v0/model_call/candidate.json'))))
    request=g.read(sealed/'request.preview.json');feedback=g.read(sealed/'feedback.json')
    model._payload=lambda *_:request
    accepted=None;decision=None;folder=out/'v1'
    try:
        call,candidate=model.call(folder/'model_call',current,'op_bit28_illegal',feedback,'native_plan_alignment_synthesis')
        if candidate is None:
            diag=g.read(folder/'model_call/interface_gate.json') if (folder/'model_call/interface_gate.json').exists() else dict(call=call)
            decision=dict(accepted=False,reasons=[dict(kind='interface_or_transport_rejected',details=diag)])
        else:
            aligned,gate=g.prior.native_flow.alignment(candidate,prep,folder/'alignment')
            g.diagnostic.audit_native(folder/'alignment',candidate,prep,'alignment')
            if not gate['accepted']:decision=dict(accepted=False,reasons=[dict(kind='native_applicability_or_target_failure')])
            else:
                h=g.old.replay(candidate,g.read(prep/'history_cases.json'),'history',folder/'history',prep)
                s=g.old.replay(candidate,g.read(prep/'search_cases.json'),'search',folder/'search',prep)
                for cohort in ('history','search'):g.diagnostic.audit_native(folder/cohort,candidate,prep,cohort)
                combined=g.prior.common.combine(h,s)
                decision=g.preserve(baseline,combined,g.read(prep/'target_preservation.private.json'),g.old.decide)
                guards={c:g.prior.native_flow.prior.all_property_guard(r,{rev:g.read(folder/c/rev/'result.json') for rev in ('before','after')},candidate) for c,r in [('history',h),('search',s)]}
                g.dump(folder/'all_property_guard.json',guards)
                for c,guard in guards.items():
                    if not guard['accepted']:
                        decision['accepted']=False;decision['reasons'].append(dict(kind='all_property_false_alarm_or_unknown',cohort=c,details=guard))
                g.dump(folder/'mapping.json',dict(history=h['mapping'],search=s['mapping']))
                if decision['accepted']:
                    accepted=candidate;g.dump(out/'accepted_candidate.json',candidate)
                    g.dump(out/'acceptance.json',dict(sha256=g.old.acceptance.sha(candidate),history=h['counts'],search=s['counts'],decision=decision))
        g.dump(folder/'decision.json',decision)
        print('CONTINUATION_RESULT',decision['accepted'],flush=True)
    finally:
        g.dump(out/'outcome.json',dict(status='accepted_development_only' if accepted else 'no_accepted_sva',calls=len(model.calls),prior_calls=1,total_calls=1+len(model.calls),decision=decision,
            accepted_candidate_sha256=g.old.acceptance.sha(accepted) if accepted else None,independent_test='not_run',formal_calls=0))
        g.dump(out/'cost.json',g.old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('--prepared',type=Path,required=True);p.add_argument('--sealed',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.prepared.resolve(),a.out.resolve())
    else:run(a.prepared.resolve(),a.sealed.resolve(),a.out.resolve())
