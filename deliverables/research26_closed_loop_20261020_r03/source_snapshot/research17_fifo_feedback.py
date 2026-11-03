"""Native sampled FIFO feedback, with independent pre-NBA state qualification.

This module does not generate or repair properties. It wraps the existing native
runner and preserves its oracle/ledger semantics. REF_TRACE is diagnostic only;
the independent port-history oracle remains the obligation authority.
"""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import re
import shutil

import research15_search_runtime as runtime
import research15_native_interface as interface
from research15_evidence import paired_ledger, marker_map, epoch_map

FIELDS=('cycle','rst','ref_count','ref_expected','drain_due','svalid','sready','sdata','mvalid','mready','mdata')
SAMPLING='All REF_TRACE values use $sampled at posedge, before nonblocking reference updates; same sampling edge as native concurrent properties.'
_BASE_EXECUTE=runtime.execute


def build(candidate,folder,depth=2,pipeline=0):
    template=runtime.testbench_template(depth,pipeline)
    fmt='REF_TRACE '+' '.join(['%0d']*len(FIELDS))
    args=', '.join('$sampled('+('native_cycle' if f=='cycle' else f)+')' for f in FIELDS)
    trace=f'\n  always @(posedge clk) if ($sampled(native_cycle)>=0) $display("{fmt}", {args});\n'
    template=template.replace('// NATIVE_PROPERTIES','// NATIVE_PROPERTIES'+trace)
    compiled=interface.compile_candidate(candidate,Path(folder),template)
    compiled['feedback_config']=dict(depth=depth,pipeline=pipeline,sampling=SAMPLING)
    interface.dump(Path(folder)/'compiled.json',compiled)
    return compiled


def parse_reference(path):
    result=[]
    if not Path(path).exists():return result
    for line in Path(path).read_text(errors='replace').splitlines():
        if not line.startswith('REF_TRACE '):continue
        fields=line.split()[1:]
        if len(fields)!=len(FIELDS):continue
        result.append({k:int(v) if re.fullmatch(r'-?\d+',v) else None for k,v in zip(FIELDS,fields)})
    return result


def qualify_sampling(trace,reference):
    """Replay pre-edge queue independently; reset changes state AFTER its edge."""
    pending=collections.deque(); mismatches=[]; checked=0
    refs={t['cycle']:t for t in reference}
    for t in trace:
        r=refs.get(t['cycle'])
        if r is None:
            mismatches.append(dict(cycle=t['cycle'],reason='missing_reference_sample'));continue
        for key in ('rst','svalid','sready','sdata','mvalid','mready','mdata'):
            if r[key]!=t[key]:mismatches.append(dict(cycle=t['cycle'],reason='port_sample_mismatch',field=key))
        if r['ref_count']!=len(pending):
            mismatches.append(dict(cycle=t['cycle'],reason='pre_NBA_count_mismatch',observed=r['ref_count'],expected=len(pending)))
        if pending and r['ref_expected']!=pending[0]:
            mismatches.append(dict(cycle=t['cycle'],reason='pre_NBA_payload_mismatch',observed=r['ref_expected'],expected=pending[0]))
        checked+=1
        if t['rst']:pending.clear();continue
        if t['mvalid'] and t['mready'] and pending:pending.popleft()
        if t['svalid'] and t['sready']:pending.append(t['sdata'])
    if len(reference)!=len(trace):mismatches.append(dict(reason='reference_length_mismatch',reference=len(reference),trace=len(trace)))
    return dict(status='passed' if checked and not mismatches else 'unknown',checked_samples=checked,
        mismatches=mismatches,sampling=SAMPLING,empty_ref_expected='undefined meaning when ref_count is zero; excluded from queue value comparison')


def coverage(record):
    trace=record['trace']; refs=record.get('reference_trace',[])
    counts=collections.Counter(record['oracle'].get('coverage',{}))
    counts['accepted_requests']=sum(bool(not t['rst'] and t['svalid'] and t['sready']) for t in trace)
    counts['accepted_responses']=sum(bool(not t['rst'] and t['mvalid'] and t['mready']) for t in trace)
    counts['presented_unaccepted_requests']=sum(bool(not t['rst'] and t['svalid'] and not t['sready']) for t in trace)
    counts['empty_reference_samples']=sum(t['ref_count']==0 and not t['rst'] for t in refs)
    counts['max_outstanding_accepted']=max((t['ref_count'] for t in refs if t['ref_count'] is not None),default=0)
    counts['drain_checkpoints']=sum(bool(t['drain_due']) for t in refs)
    counts['consecutive_request_accept_pairs']=sum(not a['rst'] and not b['rst'] and a['svalid'] and a['sready'] and b['svalid'] and b['sready'] for a,b in zip(trace,trace[1:]))
    return dict(observed=dict(counts),input_legality=record['oracle']['legality'],
        full_boundary='Input backpressure is observable; exact internal RAM-full state is not inferred from reference occupancy (read pipeline also stores data).',
        full_state_verification='unknown_without_internal_state_probe',scope='finite observed transactions; input intent alone is not acceptance')


def execute(compiled,folder,rows,mode):
    record=_BASE_EXECUTE(compiled,folder,rows,mode)
    refs=parse_reference(Path(folder)/'execute.log')
    record.update(reference_trace=refs,sampling_qualification=qualify_sampling(record['trace'],refs),
        feedback_config=compiled.get('feedback_config',{}))
    record['coverage_audit']=coverage(record)
    interface.dump(Path(folder)/'reference_trace.json',refs)
    interface.dump(Path(folder)/'sampling_qualification.json',record['sampling_qualification'])
    interface.dump(Path(folder)/'coverage_audit.json',record['coverage_audit'])
    interface.dump(Path(folder)/'replay.json',record)
    return record


def _diagnostics(record,max_windows=8):
    trigger=marker_map(record['native'],'triggers');fail=marker_map(record['native'],'failures')
    props=[]
    for a in record['candidate']['assertions']:
        props.append(dict(id=a['id'],property=a['property'],obligations=a['obligations'],
            trigger_count=len(trigger[a['id']]),failure_count=len(fail[a['id']]),
            trigger_cycles=sorted(trigger[a['id']]),failure_cycles=sorted(fail[a['id']]),
            execution_observation='empty_trigger' if not trigger[a['id']] else 'native_violation' if fail[a['id']] else 'no_violation_within_execution'))
    ep=epoch_map(record['trace']);first={}
    for v in record['oracle']['violations']:
        epoch=ep.get(v['cycle'])
        if epoch not in first:first[epoch]=v['cycle']
        first[epoch]=min(first[epoch],v['cycle'])
    first_violations=[v for v in record['oracle']['violations'] if v['cycle']==first.get(ep.get(v['cycle']))]
    relevant=sorted(set(v['cycle'] for v in first_violations)|{r['cycle'] for r in record.get('reference_trace',[]) if r['drain_due']}|set().union(*fail.values()))
    # Candidate failures can be numerous. Always keep independent target and
    # fair-drain windows before selecting illustrative candidate-only failures.
    priority=set(v['cycle'] for v in first_violations)|{r['cycle'] for r in record.get('reference_trace',[]) if r['drain_due']}
    relevant=sorted(relevant,key=lambda cycle:(cycle not in priority,cycle))
    windows=[]
    for cycle in relevant[:max_windows]:
        windows.append(dict(center_cycle=cycle,samples=[r for r in record.get('reference_trace',[]) if cycle-2<=r['cycle']<=cycle+1],
            oracle_violations=[v for v in first_violations if v['cycle']==cycle],
            associated_transactions=[t for t in record['oracle']['transactions'] if t.get('accept_cycle')==cycle or t.get('response_cycle')==cycle or t.get('cancel_cycle')==cycle or (t.get('outcome')=='pending' and any(v['cycle']==cycle and v['obligation']=='drain_no_loss' for v in first_violations))]))
    return dict(mode=record['mode'],native_status={k:record['native'].get(k) for k in ('compile_status','tool_support_status','execution_status')},
        properties=props,first_oracle_violations=first_violations,sample_windows=windows,
        omitted_window_count=max(0,len(relevant)-max_windows),sampling_qualification=record.get('sampling_qualification',{'status':'unknown'}),
        oracle_legality=record['oracle']['legality'],oracle_unknown=record['oracle']['unknown'],coverage=record.get('coverage_audit'),
        artifacts=dict(directory=record['directory'],waveform=str(Path(record['directory'])/'wave.vcd'),reference_trace=str(Path(record['directory'])/'reference_trace.json')))


def feedback(fixed,mutant,ledger=None):
    """Pure evidence feedback; no synthesized expressions or recommended property."""
    if ledger is None:ledger=paired_ledger(fixed,mutant,'feedback:caller_should_supply_stable_scenario_id')
    rows=ledger.get('ledger',[]) if isinstance(ledger,dict) else ledger
    targets=[]
    for row in rows:
        if row.get('oracle',{}).get('verdict')!='violated':continue
        aa=row.get('native',{}).get('assertions',[])
        targets.append(dict(evidence_id=row['evidence_id'],obligation=row['obligation'],cycle=row.get('cycle'),
            oracle=row['oracle'],attribution=row.get('native',{}).get('attribution_status'),assertions=aa,
            gap_observation='no_property_mapped' if not aa else 'no_effective_trigger' if not any(a.get('trigger') for a in aa) else 'triggered_without_confirmed_detection' if not any(a.get('causal_detection') is True for a in aa) else 'detected'))
    return dict(sampling_contract=SAMPLING,fixed=_diagnostics(fixed),mutant=_diagnostics(mutant) if mutant else None,
        target_evidence=targets,scope='Native sampled diagnostic evidence. Independent oracle/paired ledger determines validity. Ref_count/ref_expected logs do not replace independent obligation checks. No global proof.')


def qualify(out):
    from research15_search_experiment import stimulus
    out.mkdir(parents=True,exist_ok=False)
    source=runtime.ROOT/'deliverables/research16_ablation_20261016_r03/shared_initial.json'
    candidate=json.loads(source.read_text());shutil.copy2(source,out/'historical_model_candidate.json')
    interface.dump(out/'provenance.json',dict(candidate_source=str(source),purpose='Instrumentation qualification only; no new model generation or research success credit',sampling=SAMPLING))
    results=[]
    for depth,pipeline in ((2,0),(5,1),(4,2)):
        folder=out/f'd{depth}_p{pipeline}'; compiled=build(candidate,folder/'compiled',depth,pipeline)
        if compiled['native']['compile_status']!='passed':raise RuntimeError('native compilation failed')
        for family in ('tail_loss','backpressure','reset_pending','overlap'):
            rows=stimulus(2026101717,family)
            fixed=execute(compiled,folder/family/'correct',rows,'correct')
            mode='drop' if family=='tail_loss' else 'reset_residue' if family=='reset_pending' else 'corrupt'
            mutant=execute(compiled,folder/family/mode,rows,mode)
            ledger=paired_ledger(fixed,mutant,f'd{depth}:p{pipeline}:{family}:s2026101717')
            info=feedback(fixed,mutant,ledger)
            interface.dump(folder/family/'feedback.json',info)
            interface.dump(folder/family/'ledger.json',ledger)
            results.append(dict(depth=depth,pipeline=pipeline,family=family,
                fixed_sampling=fixed['sampling_qualification'],mutant_sampling=mutant['sampling_qualification'],
                fixed_oracle=dict(legality=fixed['oracle']['legality'],violations=len(fixed['oracle']['violations']),unknown=fixed['oracle']['unknown']),
                fixed_assertion_failures=len(fixed['native']['failures']),targets=info['target_evidence'],coverage=fixed['coverage_audit']))
            print('QUALIFIED',depth,pipeline,family,results[-1]['fixed_sampling']['status'],results[-1]['mutant_sampling']['status'],flush=True)
    passed=all(r['fixed_sampling']['status']=='passed' and r['mutant_sampling']['status']=='passed' and not r['fixed_oracle']['violations'] and not r['fixed_oracle']['unknown'] and r['fixed_oracle']['legality']=='legal' for r in results)
    summary=dict(passed=passed,compilations=3,replays=24,model_calls=0,results=results,scope='Native diagnostic instrumentation qualification, not automated refinement or independent holdout')
    interface.dump(out/'summary.json',summary);shutil.copy2(__file__,out/'research17_fifo_feedback.py')
    print(json.dumps(dict(passed=passed,compilations=3,replays=24)))
    if not passed:raise RuntimeError('sampling or legal control qualification failed')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--qualify',action='store_true');p.add_argument('--out',type=Path,default=runtime.ROOT/'deliverables/research17_feedback_qualification_20261016_r01')
    args=p.parse_args()
    if args.qualify:qualify(args.out)
