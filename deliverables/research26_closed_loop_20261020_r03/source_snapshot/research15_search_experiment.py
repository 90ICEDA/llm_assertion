"""Four equal-budget searches with coverage-feedback selection and native SVA.

All acquired inputs are development data. This module never calls a model and
never reads independent tests. Candidate-disagreement honestly falls back to
uniform exploration when the frozen initial pool has fewer than two properties.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import time
from research15_search_runtime import ROOT, RTL, MODES, OBLIGATIONS, build, execute, oracle, parse_trace, write_json, sha

OUT=ROOT/'deliverables/research15_search_20261015_r01'
METHODS=('ordinary','candidate_disagreement','raw_difference','contract_coverage')
FAMILIES=('random','overlap','backpressure','reset_pending','drain','tail_loss')
TARGET_FAMILY={'order_payload':'overlap','no_unsolicited_output':'reset_pending',
               'stall_stability':'backpressure','drain_no_loss':'tail_loss','reset_cancellation':'reset_pending'}


def stimulus(seed,family,length=112):
    rng=random.Random(seed); rows=[]; seen=set()
    init_reset=2+rng.randrange(3); reset_at=24+rng.randrange(8)
    for cycle in range(length):
        rst=int(cycle<init_reset)
        valid=int(rng.random()<.65);ready=int(rng.random()<.55)
        if family=='overlap':
            valid=int(cycle%11!=10);ready=1
        elif family=='backpressure':
            valid=int(cycle%13<11);ready=int(cycle%17>9)
        elif family=='reset_pending':
            valid=int(cycle<reset_at or cycle>reset_at+12)
            ready=int(cycle>reset_at or cycle%23>14)
            if reset_at-12<=cycle<reset_at:ready=0;valid=1
            if cycle in (reset_at,reset_at+1):rst=1;valid=0;ready=0
        elif family=='drain':
            valid=int(cycle<length//2);ready=int(cycle%7>2)
        elif family=='tail_loss':
            # Four isolated accepted requests; adequate spacing avoids source
            # intent being skipped under backpressure. A dropped final response
            # leaves no later output to expose the gap through data ordering.
            valid=int(cycle in tuple(init_reset+2+8*j for j in range(4)));ready=1
        elif family=='random' and cycle>init_reset+10 and cycle<length-30 and rng.random()<.025:
            rst=1
        if cycle>=length-24:rst=0;valid=0;ready=1
        payload=rng.getrandbits(28)*16+4
        while payload in seen:payload=rng.getrandbits(28)*16+4
        seen.add(payload)
        rows.append(dict(cycle=cycle,rst=rst,intent=valid,ready=ready,data=payload,
                         drain_due=int(cycle==length-1)))
    return rows


def native_cycle(event):
    if 'cycle' in event:return int(event['cycle'])
    match=re.search(r'cycle=(-?\d+)',event.get('detail',''))
    return int(match[1]) if match else None


def events(result,kind):
    alternatives={'failure':('failures','native_failures'),'trigger':('triggers','covers','native_covers')}
    for key in alternatives[kind]:
        if key in result:return result[key]
    return []


def adjudicate(rows,runs,candidate,scenario,persist=True):
    """Independent contract adjudication; method selection receives filtered views."""
    from research15_evidence import epoch_map
    refs={}; traces={}; errors=[]
    for mode,entry in runs.items():
        path=Path(entry['folder'])
        log=path/'execute.log'
        if not log.exists():log=path/'run.log'
        trace=parse_trace(log) if log.exists() else []
        traces[mode]=trace; refs[mode]=oracle(trace,rows)
        if persist:
            write_json(path/'independent_oracle.json',refs[mode]);write_json(path/'trace.json',trace)
        native=entry['native']
        if refs[mode]['unknown'] or refs[mode]['legality']!='legal' or native.get('compile_status')!='passed' or native.get('execution_status')!='completed':errors.append(mode)
    fixed=traces.get('correct',[]); control=refs.get('correct',{})
    assertions={a['id']:a for a in candidate['assertions']}
    mapping=[]; findings=[]; checks=collections.Counter(); effective=collections.Counter(); protected=collections.Counter()
    fixed_failures=events(runs['correct']['native'],'failure')
    fixed_healthy=control.get('legality')=='legal' and not control.get('violations') and not control.get('unknown') and runs['correct']['native'].get('execution_status')=='completed'
    fixed_epochs=epoch_map(fixed)
    for c in control.get('checks',[]):checks[c['obligation']]+=1
    fixed_failure_cycles={native_cycle(e) for e in fixed_failures}
    for hit in fixed_failures:
        fp_kind='false_positive' if fixed_healthy else 'attribution_unknown'
        findings.append(dict(semantic_key='legal/'+hit['id']+'/'+fp_kind,kind=fp_kind,cycle=native_cycle(hit),
            assertion_id=hit['id'],obligation='legal_transaction',variant='correct',scenario=scenario,
            legal=control.get('legality')=='legal',independent_control=control.get('verdict'),
            attribution='native failure on independently legal correct FIFO' if fixed_healthy else 'control legality or execution unknown'))
    for hit in events(runs['correct']['native'],'trigger'):
        item=assertions.get(hit['id'],{})
        cycle=native_cycle(hit)
        if cycle is None:continue
        delay=int('|=>' in item.get('property',''))
        for o in item.get('obligations',[]):
            if any(c['cycle']==cycle+delay and c['obligation']==o for c in control.get('checks',[])):
                effective[o]+=1
    for mode in MODES[1:]:
        ref=refs[mode];trace=traces[mode]
        equal_inputs=bool(fixed) and len(fixed)==len(trace) and all(
            all(t[n]==u[n] for n in ('rst','svalid','sready','sdata','mready')) for t,u in zip(trace,fixed))
        failures=events(runs[mode]['native'],'failure')
        fail_cycles={native_cycle(e) for e in failures}
        epochs=epoch_map(trace);first={}
        for v in ref['violations']:
            ep=epochs.get(v['cycle'])
            if ep is not None:first[ep]=min(first.get(ep,v['cycle']),v['cycle'])
        clean=equal_inputs and not control.get('violations') and not control.get('unknown') and ref['legality']=='legal'
        for v in ref['violations']:
            cycle,o=v['cycle'],v['obligation']
            epoch=epochs.get(cycle)
            hits=[e['id'] for e in failures if native_cycle(e)==cycle and o in assertions.get(e['id'],{}).get('obligations',[])]
            prior_alarm=any(c is not None and epochs.get(c)==epoch and c<cycle for c in fail_cycles)
            same_cycle_ids=[e['id'] for e in failures if native_cycle(e)==cycle]
            fixed_prefix_clean=not any(c is not None and fixed_epochs.get(c)==epoch and c<=cycle for c in fixed_failure_cycles)
            triggered_hits=[aid for aid in hits if any(e['id']==aid and native_cycle(e)==cycle-assertions[aid].get('derived_delay',0)
                and epochs.get(native_cycle(e))==epoch for e in events(runs[mode]['native'],'trigger'))]
            first_in_epoch=cycle==first.get(epoch)
            causal=bool(triggered_hits) and clean and fixed_prefix_clean and first_in_epoch and not prior_alarm
            # An alarm mapped to another atomic obligation is not a silent
            # miss. Earlier rejected prefixes also cannot establish a new FN.
            silent_prefix=not any(c is not None and epochs.get(c)==epoch and c<=cycle for c in fail_cycles)
            classification='causal_detection' if causal else 'false_negative' if silent_prefix and clean and fixed_prefix_clean and first_in_epoch else 'attribution_unknown'
            if causal:protected[o]+=1
            txn=next((x for x in ref['transactions'] if x['transaction_id']==v.get('transaction_id')),None)
            item=dict(semantic_key=f'{mode}/{o}/{classification}',kind=classification,
                obligation=o,variant=mode,scenario=scenario,cycle=cycle,epoch=epoch,first_violation_in_epoch=first_in_epoch,transaction_id=v.get('transaction_id'),
                transaction=txn,oracle_details=v,legal=ref['legality']=='legal',same_input_schedule=equal_inputs,
                independent_fixed=control.get('verdict'),independent_buggy='violation',assertion_ids=hits,
                all_native_failure_ids_same_cycle=same_cycle_ids,candidate_prefix_accepted=silent_prefix,
                trigger_measurement='native cover action for parsed assertion antecedent',
                clean_first_violation_credit=causal)
            mapping.append(item)
            if clean:findings.append(item)
    # Native candidate disagreement is only between >=2 frozen properties.
    reject_vectors={m:[bool([e for e in events(runs[m]['native'],'failure') if e['id']==a['id']]) for a in candidate['assertions']] for m in MODES}
    disagreement=sum(len(set(v))>1 for v in reject_vectors.values()) if len(assertions)>1 else 0
    diff_count=sum(any(t[n]!=u[n] for n in ('mvalid','mdata','sready'))
        for m,ts in traces.items() if m!='correct' for t,u in zip(ts,fixed)
        if not t['rst'] and ((t['mvalid'] or u['mvalid']) or t['sready']!=u['sready']))
    return dict(status='unknown' if errors else 'ok',errors=errors,findings=findings,mapping=mapping,
        semantic_keys=sorted({f['semantic_key'] for f in findings}),
        obligation_gap_keys=sorted({f"{f['variant']}/{f['obligation']}" for f in mapping if f['kind']=='false_negative' and f['same_input_schedule'] and f['legal']}),
        fixed_obligation_checks=dict(checks),effective_native_triggers=dict(effective),causal_protected=dict(protected),
        raw_difference_count=diff_count,candidate_disagreement_count=disagreement,reject_vectors=reject_vectors,
        coverage={m:r['coverage'] for m,r in refs.items()},reference_verdicts={m:r['verdict'] for m,r in refs.items()})


class Policy:
    """Every decision consumes only the method's declared observation view."""
    def __init__(self,method,seed):
        self.method=method;self.rng=random.Random(seed);self.history=[];self.count=collections.Counter()
        self.checks=collections.Counter();self.triggers=collections.Counter();self.protected=collections.Counter();self.witnesses=set()

    def choose(self):
        target=None;scores={}
        if self.method=='contract_coverage':
            for o in OBLIGATIONS:
                seen=any(key.endswith('/'+o) for key in self.witnesses)
                # Selection is feedback-sensitive: unseen oracle obligations,
                # missing effective triggers and unprotected targets each add
                # deficit. Repeated attempts reduce this arm's value.
                deficit=3*int(self.checks[o]==0)+2*int(self.triggers[o]==0)+2*int(self.protected[o]==0)+int(not seen)
                scores[o]=deficit/(1+self.count[o])
            maximum=max(scores.values());eligible=[o for o in OBLIGATIONS if scores[o]==maximum]
            target=self.rng.choice(eligible);family=TARGET_FAMILY[target];self.count[target]+=1
            reason='maximum current obligation deficit / prior attempts; recomputed from own acquired evidence'
        elif self.method in ('candidate_disagreement','raw_difference') and self.history and self.rng.random()>.35:
            field='candidate_disagreement_count' if self.method=='candidate_disagreement' else 'raw_difference_count'
            best=max(x[field] for x in self.history)
            if best>0:
                family=self.rng.choice([x['family'] for x in self.history if x[field]==best]);reason='exploit largest permitted historical score'
            else:family=self.rng.choice(FAMILIES);reason='no positive permitted score; uniform exploration'
        else:family=self.rng.choice(FAMILIES);reason='uniform exploration'
        return dict(family=family,target_obligation=target,reason=reason,deficit_scores=scores,
                    history_queries=len(self.history),selection_uses_no_unexecuted_oracle=True)

    def update(self,family,result):
        if self.method=='ordinary':view=dict(family=family)
        elif self.method=='candidate_disagreement':view=dict(family=family,candidate_disagreement_count=result['candidate_disagreement_count'])
        elif self.method=='raw_difference':view=dict(family=family,raw_difference_count=result['raw_difference_count'])
        else:
            if result.get('status','ok')=='ok':
                self.checks.update(result['fixed_obligation_checks']);self.triggers.update(result['effective_native_triggers']);self.protected.update(result['causal_protected'])
                self.witnesses.update(result['obligation_gap_keys'])
            view=dict(family=family,status=result.get('status','ok'),checks=dict(self.checks),triggers=dict(self.triggers),protected=dict(self.protected),witnesses=sorted(self.witnesses),
                protection_measure='declared-obligation/native-cover/independent-oracle observation proxy; not semantic entailment')
        self.history.append(view)
        return view


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--out',type=Path,default=OUT);ap.add_argument('--budget',type=int,default=6)
    ap.add_argument('--engineering',action='store_true');args=ap.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    import research15_native_interface as interface
    candidate=interface.normalize_candidate(json.loads(args.candidate.read_text()));write_json(out/'initial_candidate.json',candidate)
    shutil.copy2(RTL,out/'axis_fifo.v')
    for f in (Path(__file__),*[ROOT/'scripts'/name for name in ('research15_search_runtime.py','research15_native_interface.py','research15_evidence.py','research15_acceptance.py','research_native_runner.py')]):
        shutil.copy2(f,out/(f.name+'.snapshot'))
    specs=[dict(seed=2026101507,depth=2,pipeline=0),dict(seed=2026101531,depth=5,pipeline=1)]
    protocol=dict(methods=METHODS,specs=specs,queries_per_method_per_seed=args.budget,
        query_cost='one input schedule, correct plus four artificial faults = five native executions; all executed queries charged including unknown/duplicates',
        planned_queries=len(METHODS)*len(specs)*args.budget,planned_replays=5*len(METHODS)*len(specs)*args.budget,
        compile_bootstrap_executions=len(specs),finite_drain_scope='actual RAM<=8, RAM_PIPELINE<=2, OUTPUT_FIFO_ENABLE=0; require >=18 true input-idle/ready samples, generated suffix24',
        source_sha256=sha(RTL),candidate_sha256=sha(args.candidate),candidate_source_path=str(args.candidate.resolve()),candidate_origin='engineering_qualification' if args.engineering else 'real_model_generated_external_candidate',
        input_grammar=FAMILIES,shared_information='identical candidate/specification/RTL/interface/grammar and budgets; method-specific feedback view restricted in Policy.update',
        dedup='one independent gap per artificial fault mode and violated obligation; repeated cycles, seeds, families and configurations are replications',
        candidate_disagreement_eligible=len(candidate['assertions'])>1,
        candidate_disagreement_limit='one initial property has no candidate pairs; baseline then explicitly uniform fallback',
        split='development_only; not independent testing; do not leak acquired feedback to no-search ablation arms',
        historical_fifo_presented='unknown, these are artificial output-boundary mutations',
        parameter_capacity='depth5 rounds to8; depth2 actual2; pipeline storage additional')
    write_json(out/'protocol.json',protocol)
    records=[];compile_cost=[]
    for spec in specs:
        compiled_path=out/'compiled'/f'd{spec["depth"]}_p{spec["pipeline"]}'
        compiled=build(candidate,compiled_path,spec['depth'],spec['pipeline']);compile_cost.append(compiled)
        if compiled['native']['compile_status']!='passed':
            write_json(out/'compile_failure.json',compiled);raise RuntimeError('Native compilation failed; no simulation outcome claimed')
        for method in METHODS:
            policy=Policy(method,spec['seed']);seen_gaps=set();seen_semantic=set()
            for q in range(args.budget):
                folder=out/'queries'/f's{spec["seed"]}'/method/f'q{q:02}'
                folder.mkdir(parents=True)
                selection=policy.choose();rows=stimulus(spec['seed']+q*1009,selection['family'])
                write_json(folder/'selection_before_execution.json',selection);write_json(folder/'stimulus.json',rows)
                runs={}
                for mode in MODES:
                    path=folder/mode
                    replay=execute(compiled,path,rows,mode)
                    runs[mode]=dict(folder=str(path),native=replay['native'])
                adjudication=adjudicate(rows,runs,candidate,str(folder.relative_to(out)))
                view=policy.update(selection['family'],adjudication)
                gaps=set(adjudication['obligation_gap_keys']);semantic=set(adjudication['semantic_keys'])
                result=dict(seed=spec['seed'],depth=spec['depth'],pipeline=spec['pipeline'],method=method,query=q,
                    selection=selection,permitted_feedback_view=view,new_independent_gap_keys=sorted(gaps-seen_gaps),
                    duplicate_gap_keys=sorted(gaps&seen_gaps),new_semantic_keys=sorted(semantic-seen_semantic),
                    evidence=adjudication,cost=dict(native_replays=5,model_calls=0,model_tokens=None,
                        native_simulation_wall_seconds=sum(x['native'].get('execute',{}).get('wall_seconds',0) for x in runs.values())),folder=str(folder.relative_to(out)))
                seen_gaps.update(gaps);seen_semantic.update(semantic)
                write_json(folder/'result.json',result);records.append(result)
                print(method,spec['seed'],q,selection['family'],len(result['new_independent_gap_keys']),adjudication['status'],flush=True)
    write_json(out/'results.json',records)
    summary=[]
    for method in METHODS:
        subset=[r for r in records if r['method']==method]
        gaps={k for r in subset for k in r['evidence']['obligation_gap_keys']}
        allkeys={k for r in subset for k in r['evidence']['semantic_keys']}
        summary.append(dict(method=method,queries=len(subset),native_replays=5*len(subset),
            independent_gap_keys=sorted(gaps),independent_gap_count=len(gaps),semantic_classes=sorted(allkeys),
            duplicate_gap_observations=sum(len(r['duplicate_gap_keys']) for r in subset),
            unknown_queries=sum(r['evidence']['status']!='ok' for r in subset),
            native_simulation_wall_seconds=sum(r['cost']['native_simulation_wall_seconds'] for r in subset),
            selected_families=dict(collections.Counter(r['selection']['family'] for r in subset))))
    write_json(out/'summary.json',summary)
    write_json(out/'compile_results.json',compile_cost)
    # Only this contract feedback artifact is predeclared for search-enabled
    # refinement arms. No-search arms must never read it or results.json.
    export=[dict(scenario=r['folder'],selection=r['selection'],new_independent_gap_keys=r['new_independent_gap_keys'],
        examples=r['evidence']['mapping'][:8],fixed_false_positives=[f for f in r['evidence']['findings'] if f['kind']=='false_positive'][:5])
        for r in records if r['method']=='contract_coverage']
    write_json(out/'search_enabled_arms_only.json',dict(allowed_arms=['B','D'],split='development',queries=export))
    witness=None
    for r in records:
        if r['method']!='contract_coverage' or r['selection']['family']!='tail_loss':continue
        items=[e for e in r['evidence']['mapping'] if e['variant']=='drop' and e['obligation']=='drain_no_loss' and e['kind']=='false_negative']
        if not items:continue
        query_dir=out/r['folder']
        drop_ref=json.loads((query_dir/'drop/independent_oracle.json').read_text())
        if any(v['obligation']!='drain_no_loss' for v in drop_ref['violations']):continue
        witness=dict(rows=json.loads((query_dir/'stimulus.json').read_text()),mode='drop',depth=r['depth'],pipeline=r['pipeline'],
            scenario_id=r['folder'],source_query_directory=str(query_dir),source_method='contract_coverage',
            initial_candidate_sha256=protocol['candidate_sha256'],initial_no_alarm_through_violation=True,
            fixed_replay=str(query_dir/'correct'),mutant_replay=str(query_dir/'drop'),
            actual_query_cost=dict(this_query_native_executions=5,method_queries_through_discovery=r['query']+1,
                method_native_executions_through_discovery=5*(r['query']+1),
                complete_comparative_search_queries=protocol['planned_queries'],complete_comparative_search_executions=protocol['planned_replays']),
            first_violation=items[0],cost_sharing='one actually acquired witness shared by B/D; do not count as independently acquired per arm')
        break
    write_json(out/'treatment_witness.json',witness)
    compiled_seconds=sum(x['native'].get('compile',{}).get('wall_seconds',0) for x in compile_cost)
    write_json(out/'cost.json',dict(queries=len(records),native_replays=5*len(records),native_compilations=len(compile_cost),
        native_compile_wall_seconds=compiled_seconds,native_simulation_wall_seconds=sum(r['cost']['native_simulation_wall_seconds'] for r in records),
        bootstrap_native_executions=len(compile_cost),model_calls_in_search=0,model_tokens_in_search=None,
        shared_model_generation_cost='external initial generation/qualification; see candidate_source_path and native experiment model-call artifacts',formal_calls=0))
    report=['# Coverage-feedback FIFO search: actual native execution','',
        'All inputs are development data. The shared model candidate is fixed for all methods. Faults are explicitly artificial output-boundary changes to real vendored axis_fifo RTL.', '',
        '| Method | Queries | Native replays | Independent missed gap classes | Duplicate gap observations | Unknown queries |',
        '|---|---:|---:|---:|---:|---:|']
    for s in summary:report.append(f'| {s["method"]} | {s["queries"]} | {s["native_replays"]} | {s["independent_gap_count"]} | {s["duplicate_gap_observations"]} | {s["unknown_queries"]} |')
    report+=['','Independent gap class = (artificial fault, violated obligation), not waveform/seed/cycle count. First violation per reset epoch is the attribution boundary; later violations are preserved as unknown. A native alarm for another named obligation is not counted as a silent false negative.','',
        'Contract selection uses accumulated observed obligation checks, native antecedent cover events and first-violation evidence. Deficits are recalculated after each own query, divided by prior target attempts. The exact input to each policy is stored in permitted_feedback_view; ordinary/disagreement/difference cannot read contract adjudication.', '',
        'The single-property initial pool has no candidate disagreement pair, so that arm honestly falls back to uniform exploration. This does not replace the existing 11-pair comparison.', '',
        'Native cover confirms finite sampled antecedent activation, not semantic entailment or global protection. The declared obligation mapping remains a proxy. RAM depth5 rounds to8; finite drain requires at least18 actual input-idle/ready samples within the explicitly bounded depth/pipeline configuration.', '',
        'Treatment witness: '+('actually found; treatment_witness.json records source query and input' if witness else 'not found; treatment_witness.json is null; no engineering substitution'), '',
        'No independent-test outcome is reported here. B/D may share the actual acquisition with shared cost; A/C must not read the acquisition artifact. No formal proof or historical original FIFO bug validation is claimed.']
    (out/'REPORT.md').write_text('\n'.join(report)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
