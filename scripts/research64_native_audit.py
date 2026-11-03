"""Independent record audit for research64; no model or native executions.

Recomputes transaction references and witnesses from saved native logs. Audit
reference work is charged separately, never presented as experiment selection.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
import time
import research64_search_value as run


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False)
    run.verify(root)
    assert run.read(root/'outcome.json')['status']=='completed'
    checks=[];oracle_calls=0;sampling_calls=0;ledger_calls=0;seconds=0.;verified=0
    def check(name,value):
        assert value,name
        checks.append(dict(name=name,passed=True))
    registry=run.read(root/'public_feedback.json')
    records=[]
    for pair,pub in registry.items():
        for i,r in enumerate(pub['results']):records.append((root/'public'/pair/f'q{i}',r))
    for r in run.read(root/'records.json'):
        records.append((root/'queries'/r['pair']/f"s{r['seed']}"/r['method']/f"q{r['query']}",r))
    for folder,result in records:
        first,second=result['pair'].split('__');rr={}
        for name in (first,second):
            rr[name]={}
            for mode in run.MODES:
                path=folder/name/mode;record=run.read(path/'replay.json');rr[name][mode]=record
                trace=run.extension.runtime.parse_trace(path/'execute.log')
                refs=run.loop.runtime.parse_reference(path/'execute.log')
                assert trace==record['trace'] and refs==record['reference_trace'],str(path)
                rows=run.read(folder/name/(mode+'_stimulus')/'stimulus.json')
                if isinstance(rows,dict):rows=rows['rows']
                t=time.perf_counter();o=run.extension.runtime.oracle(trace,rows);oracle_calls+=1
                sample=run.loop.runtime.qualify_sampling(trace,refs);sampling_calls+=1;seconds+=time.perf_counter()-t
                assert o==record['oracle'] and sample==record['sampling_qualification'],str(path)
                native=record['native'];log=(path/'execute.log').read_text()
                for field,marker in (('failures','ASSERT_FAIL'),('triggers','TRIGGER')):
                    parsed={(m[0],int(m[1])) for m in re.findall(r'^'+marker+r' (\S+) cycle=(-?\d+)',log,re.M)}
                    stored={(m['id'],int(re.search(r'cycle=(-?\d+)',m['detail'])[1])) for m in native[field]}
                    assert parsed==stored,str(path)+field
                assert native['execution_status']=='completed' and 'NATIVE_RUN_COMPLETE' in log
                assert (path/'wave.vcd').stat().st_size>0
                verified+=1
        confirmed=[];unknown=later=0
        for mode in run.MODES[1:]:
            t=time.perf_counter();g=run.evidence.paired_ledger(rr[first]['correct'],rr[first][mode],str(folder.relative_to(run.ROOT))+':'+mode)
            ledger_calls+=1;seconds+=time.perf_counter()-t
            info=run.loop.inspect(g['ledger']);unknown+=len(info['unknown']);later+=len(g['exclusions'])
            saved=run.read(folder/'judgements'/f'{mode}.json')
            assert saved['stats']==g['stats'] and saved['exclusions']==g['exclusions']
            for k in sorted(info['misses']):
                row=info['rows'][k];v=run.prior.validate_gap(row,rr[first]['correct'],rr[first][mode])
                if result['healthy'] and result['correct_accepts'][first] and v['valid']:
                    confirmed.append((run.key(run.read(root/'candidates'/f'{first}.json'),'FN',row['obligation'],mode),k))
        check(str(folder.relative_to(root))+':witnesses',sorted(confirmed)==sorted((g['key'],g['evidence']['evidence_id']) for g in result['gaps'] if g['kind']=='FN'))
        fp=set()
        if result['healthy']:
            fault_class='legal_reset' if result['family']=='reset_pending' else 'legal_stall' if result['family']=='backpressure' else 'legal_transaction'
            marks=run.evidence.marker_map(rr[first]['correct']['native'],'failures')
            for a in rr[first]['correct']['candidate']['assertions']:
                if marks.get(a['id']):
                    for ob in a['obligations']:fp.add(run.key(run.read(root/'candidates'/f'{first}.json'),'FP',ob,fault_class))
        check(str(folder.relative_to(root))+':false_alarms_and_dedup',set(result['gap_keys'])=={k for k,_ in confirmed}|fp)
        check(str(folder.relative_to(root))+':unknown',unknown==result['unknown'] and later==result['later_attribution_unknown'])
        expected_xor=sum(len(run.prior.failures(rr[first][m]) ^ run.prior.failures(rr[second][m])) for m in run.MODES)
        check(str(folder.relative_to(root))+':whole_candidate_disagreement',expected_xor==result['candidate_disagreement_count'])
    # Semantic checks of selection information isolation and duration deduplication.
    check('long_short_not_extra_mechanisms',all(run.mechanism('long_'+m)==run.mechanism(m) for m in ('valid_withdraw_stalled','valid_withdraw_release')))
    public=next(iter(registry.values()))['results'][0]
    changed=copy.deepcopy(public)
    changed.update(fixed_obligation_checks={},effective_native_triggers={},causal_protected={},obligation_gap_keys=['injected/private_answer'],maximum_stall=255)
    for m in ('ordinary','candidate_disagreement','raw_difference'):
        a=run.grammar.Policy(m,6401);b=run.grammar.Policy(m,6401)
        run.update(a,m,'overlap',public);run.update(b,m,'overlap',changed)
        check(m+':private_judge_cannot_change_choice',run.decision(a,m,6401,0,a.history)==run.decision(b,m,6401,0,b.history))
    model=run.grammar.Policy('contract_coverage',6401)
    base=run.update(model,'contract_coverage','overlap',public)
    checkpoint=copy.deepcopy(model)
    first_choice=run.decision(copy.deepcopy(model),'contract_coverage',6401,0,[base])
    effects=[]
    for ob in run.grammar.OBLIGATIONS:
        altered=copy.deepcopy(checkpoint)
        altered.checks[ob]=0;altered.triggers[ob]=0;altered.protected[ob]=0
        effects.append(run.decision(altered,'contract_coverage',6401,0,[base])!=first_choice)
    # Merely record sensitivity; a zero result is not changed into a passing claim.
    run.dump(out/'audit.json',dict(passed=True,checks=checks,native_replays_verified=verified,
        transaction_reference_calls=oracle_calls,sampling_reference_calls=sampling_calls,paired_judge_calls=ledger_calls,
        reference_wall_seconds=seconds,new_native_executions=0,model_calls=0,formal_calls=0,
        diagnostic_contract_feedback_sensitivity=any(effects),scope='Audit cost separate from selection/measurement experiment cost.'))
    print('AUDIT',len(checks),verified,'native logs checked',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
