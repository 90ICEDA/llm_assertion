"""Archive-decision regression plus fresh native replay; zero model calls."""
import argparse
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash,bind_measurement,ROOT
from research196_component_guard import runtime
from research195_refinement_fixtures import FixtureAdapter


def run(out, fresh=False):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    origin=ROOT/'deliverables/research195_refinement_execute_20261103_r01'
    rows=[];bindings={}
    source_names=['research196_component_guard.py','research196_guard_qualify.py','research195_refinement_adapter.py','research194_refinement.py']
    dump(out/'protocol.json',dict(new_model_calls=0,heldout_read=False,
        sources={n:file_hash(ROOT/'scripts'/n) for n in source_names},
        scope='Runtime replay of existing development proposals, then four preregistered fresh native proposal regressions. No new LLM claims.',
        fresh_ids=['window/19507/F','window/19507/L','single_inflight_match/19507/L','exception/19507/L'] if fresh else []))
    for rd in sorted(origin.glob('*/*/*/refinement/round01')):
        if not (rd/'proposal_native/measurement.json').exists():continue
        identity='/'.join(rd.relative_to(origin).parts[:3]);name,seed,arm=identity.split('/')
        baseline=read(rd/'current_measurement.json');proposal=read(rd/'proposal.json')
        request=read(rd/'request.preview.json')
        import json
        context=json.loads(request['messages'][-1]['content'])
        # The saved initial state is also the active candidate of this one-round experiment.
        state=read(ROOT/'deliverables/research195_refinement_prepare_20261103_r01'/name/seed/arm/'state.json')
        before=state['initial'];measured=bind_measurement(read(rd/'proposal_native/measurement.json'),proposal)
        for p in (rd/'current_measurement.json',rd/'proposal.json',rd/'proposal_native/measurement.json'):
            bindings[str(p)]=file_hash(p)
        decisions={}
        for on in (False,True):
            core,_=runtime(arm,on);ctl=core.Controller(before,'R3',FixtureAdapter(name).case['obligations'],
                protected=set(baseline['detected_ids']),protected_transactions=set(baseline.get('transaction_detected_ids',[])),max_rounds=1)
            entry=ctl.observe(proposal,measured,baseline=baseline)
            decisions['on' if on else 'off']=entry['decision']
        row=dict(id=identity,archived_response=True,new_model_calls=0,decisions=decisions)
        if fresh and identity in read(out/'protocol.json')['fresh_ids']:
            adapter=FixtureAdapter(name)
            rerun=adapter.evaluate(proposal,out/'fresh'/identity/'native',state['queries'])
            core,_=runtime(arm,True);ctl=core.Controller(before,'R3',adapter.case['obligations'],
                protected=set(baseline['detected_ids']),protected_transactions=set(baseline.get('transaction_detected_ids',[])),max_rounds=1)
            row.update(fresh_decision=ctl.observe(proposal,rerun,baseline=baseline)['decision'],fresh_cost=rerun['cost'])
        rows.append(row);dump(out/'results.json',rows)
    if any(file_hash(p)!=h for p,h in bindings.items()):raise ValueError('archived_input_changed')
    dump(out/'source_bindings.json',bindings)
    transitions=[r['id'] for r in rows if r['decisions']['off']['accepted'] and not r['decisions']['on']['accepted']]
    expected=['window/19507/L','window/19519/L']
    dump(out/'outcome.json',dict(status='passed' if sorted(transitions)==expected and all(r.get('fresh_decision',r['decisions']['on'])['accepted']==r['decisions']['on']['accepted'] for r in rows) else 'regression_mismatch',
        natively_measured_proposals=len(rows),old_accepted=sum(r['decisions']['off']['accepted'] for r in rows),new_accepted=sum(r['decisions']['on']['accepted'] for r in rows),
        changed_decisions=transitions,expected_changed_decisions=expected,new_model_calls=0,
        fresh_native_jobs=sum(r.get('fresh_cost',{}).get('native_execution_attempts',0) for r in rows)))
    print(read(out/'outcome.json'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--fresh',action='store_true')
    a=p.parse_args();run(a.out,a.fresh)
