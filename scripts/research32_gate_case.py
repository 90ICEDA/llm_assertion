"""Re-execute one archived genuine model proposal, not a newly generated repair.

Retrospective development case selection is explicit: choose the first current
case repaired without local errors, then the first previously legal historical
case with a new false alarm. Test the same proposal under both decision rules.
"""
import argparse
import hashlib
import shutil
from pathlib import Path
import research17_loop as loop
import research31_gate as gate
import research32_runtime as extension
from research26_model import replace_one

read,dump=loop.read,loop.dump
SOURCE=loop.ROOT/'deliverables/research27_closed_loop_20261020_r06'


def main(out):
    loop.prepare(out)
    for name in ('research32_gate_case.py','research31_gate.py','research32_runtime.py','research28_valid_runtime.py','research20_stall_runtime.py'):
        shutil.copy2(loop.ROOT/'scripts'/name,out/'source_snapshot'/name)
    initial=read(SOURCE/'shared_initial.json')
    proposal=read(SOURCE/'core/v0/model_call/candidate.json')
    edit=read(SOURCE/'core/v0/model_call/model_edit.json')
    assert replace_one(edit,initial)==proposal
    assert read(SOURCE/'core/v0/model_call/result.json')['status']=='response_received'
    cases=read(SOURCE/'development_plan.json'); eligible=[]; regressions=[]
    for i,c in enumerate(cases):
        old=loop.inspect(read(SOURCE/f'core/before/case_{i}/ledger.json')['ledger'])
        new=loop.inspect(read(SOURCE/f'core/v0/native/case_{i}/ledger.json')['ledger'])
        if old['misses'] and not (new['misses'] or new['false_positives'] or new['unknown']):eligible.append(i)
        if not old['false_positives'] and new['false_positives']:regressions.append(i)
    assert eligible and regressions
    current_idx,history_idx=eligible[0],regressions[0]
    selected=[cases[current_idx],cases[history_idx]]
    dump(out/'cases.json',selected);dump(out/'initial.json',initial);dump(out/'archived_proposal.json',proposal)
    dump(out/'provenance.json',dict(source=str(SOURCE),current_index=current_idx,historical_index=history_idx,
        selection='Retrospective first qualifying current repair and first historical new-FP case; not random or prospective mechanism effect.',
        raw_sources={str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [SOURCE/'shared_initial.json',SOURCE/'core/v0/model_call/model_edit.json',SOURCE/'core/v0/model_call/response.assembled.json',SOURCE/'core/v0/model_call/result.json']},
        model_calls_new=0,model_proposal_unmodified=True))
    with extension.installed():
        before=loop.replay(initial,out/'core/before',selected)
        after=loop.replay(proposal,out/'core/after',selected)
    old=loop.inspect(before['group']['ledger']);new=loop.inspect(after['group']['ledger'])
    targets=sorted(k for k in old['misses'] if old['rows'][k]['scenario_id']==selected[0]['id'])
    def current_only(result):
        rows=[r for r in result['group']['ledger'] if r['scenario_id']==selected[0]['id']]
        info=loop.inspect(rows)
        return not (info['misses'] or info['false_positives'] or info['unknown']) and all(h['okay'] for h in result['health'] if h['scenario']==selected[0]['id'])
    verdict=gate.decide(before['group']['ledger'],after['group']['ledger'],targets)
    dump(out/'gate.json',verdict)
    example_keys=sorted(new['false_positives']-old['false_positives'])
    result=dict(status='archived_natural_proposal_native_replay_completed',
        current_repair_accepts=current_only(after),full_gate_accepts=verdict['accepted'],
        current_target_keys=targets,before=before['counts'],after=after['counts'],
        historical_new_false_alarm_rows=len(example_keys),first_false_alarm=new['rows'][example_keys[0]] if example_keys else None,
        reasons=[r['kind'] for r in verdict['reasons']],
        scope='Same actual model proposal on two declared retrospective development cases; proves a recorded failure the gate rejects, not frequency or prospective model stability.',
        new_model_calls=0,formal_calls=0)
    dump(out/'outcome.json',result)
    assert result['current_repair_accepts'] and not result['full_gate_accepts'] and result['historical_new_false_alarm_rows']>0
    print({k:v for k,v in result.items() if k not in ('current_target_keys','first_false_alarm')},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    main(out)
