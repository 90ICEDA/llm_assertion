"""Cost-only checkpoint registration before acceptance; no model calls.

Actual tokens and charged service seconds are separate axes. Service seconds
include acquired queries, native proposal replay and remote-call elapsed time;
they exclude scheduler lock wait, shared-baseline reuse and orchestration I/O.
They are not total elapsed campaign wall time. Unknown usage is never zero.
"""
import argparse
import copy
from pathlib import Path
import statistics
from research194_refinement_runner import ROOT,read,dump,file_hash
from research194_refinement import digest
from research194_active_search import combine_candidates,project_measurement
from research194_metrics import temporal_detection

GROUPS={'R':{'R0':'S0_R0','R1':'S0_R1','R2':'S0_R2','R3':'S0_R3'},
        'S':{'S0':'S0_R1','S1':'S1_R1','S2':'S2_R1','S3':'S3_R1'},
        'A':{'A0':'S0_R1','A1':'S3_R1','A2':'S0_R3','A3':'S3_R3'}}


def optional(path,default):return read(path) if Path(path).exists() else default


def select(points,axis,budget):
    valid=[p for p in points if p[axis] is not None and p[axis]<=budget]
    return max(valid,key=lambda p:p['round'])


def register(prepared,execution,out):
    prepared,execution,out=map(Path,(prepared,execution,out))
    if out.exists():raise ValueError('immutable_cost_registration_exists')
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('population_not_frozen')
    protocol=read(prepared/'protocol.json');runs=[];candidates={};bindings={}
    def load(p):bindings[str(p.resolve())]=file_hash(p);return read(p)
    for e in protocol['entries']:
        folder=execution/e['id']/'refinement';outcome=load(folder/'outcome.json');prepared_state=load(Path(e['state']));initial=prepared_state['initial']
        rounds=optional(folder/'rounds.json',[]);costs=optional(folder/'cost_components.json',[])
        state=copy.deepcopy(initial);tokens=0;seconds=0;points=[]
        def checkpoint(index,status):
            h=digest(state);candidates.setdefault(e['case_id'],{})[h]=copy.deepcopy(state)
            return dict(round=index,status=status,candidate_sha256=h,tokens=tokens,service_seconds=seconds)
        points.append(checkpoint(0,'initial'))
        if not rounds and e['mode']=='blocked_unknown':
            # The first query was paid before preparation even when no model is
            # permitted. Charge its logical service cost; physical reuse is zero.
            seconds=prepared_state['first_acquisition']['cost']['r196_total_seconds']
            points.append(checkpoint(1,'not_attempted_unknown_initial'))
        for r in rounds:
            index=r['round'];rd=folder/f'round{index:02}'
            paid=optional(rd/'model_call/result.json',None)
            if paid is not None:
                load(rd/'model_call/result.json')
                prompt,completion=paid.get('prompt_tokens'),paid.get('completion_tokens')
                tokens=tokens+prompt+completion if tokens is not None and isinstance(prompt,int) and isinstance(completion,int) else None
                seconds=seconds+paid['wall_seconds'] if seconds is not None and isinstance(paid.get('wall_seconds'),(int,float)) else None
            elif r.get('model',{}).get('model_calls'):
                tokens=None;seconds=None
            for c in costs:
                if c.get('round')!=index:continue
                if c['purpose']=='acquisition':value=c.get('r196_total_seconds')
                elif c['purpose']=='proposal_history':value=c.get('wall_seconds')
                else:value=0
                seconds=seconds+value if seconds is not None and isinstance(value,(int,float)) else None
            if r.get('status')=='infrastructure_interrupted':seconds=None
            if r.get('status')=='accepted':state=load(rd/'proposal.json')
            points.append(checkpoint(index,r.get('status','unknown')))
        frozen=load(folder/'frozen.json')
        if digest(state)!=digest(frozen):raise ValueError('checkpoint_frozen_mismatch:'+e['id'])
        runs.append(dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],arm=e['search']+'_'+e['strategy'],points=points,
            terminal_status=outcome.get('termination_reason',outcome['status']),final_tokens=tokens,final_service_seconds=seconds))
    sections=[]
    for group,arms in GROUPS.items():
        for cid in protocol['case_ids']:
            for seed in protocol['seeds']:
                matched={a:next(r for r in runs if r['case_id']==cid and r['seed']==seed and r['arm']==arm) for a,arm in arms.items()}
                for axis,grid in [('tokens',(0,65536,131072,262144)),('service_seconds',(0,120,240,480))]:
                    finals=[r['points'][-1][axis] for r in matched.values()]
                    budgets=[(str(v),v) for v in grid]
                    if all(v is not None for v in finals):budgets.append(('minimum_observed_total',min(finals)))
                    for name,budget in budgets:
                        sections.append(dict(group=group,case_id=cid,seed=seed,axis=axis,budget_label=name,budget=budget,
                            common_observed_support=all(v is not None and v>=budget for v in finals),
                            known_final_costs=all(v is not None for v in finals),
                            checkpoints={a:select(r['points'],axis,budget) for a,r in matched.items()}))
    used={(s['case_id'],p['candidate_sha256']) for s in sections for p in s['checkpoints'].values()}
    candidates={c:{h:v for h,v in versions.items() if (c,h) in used} for c,versions in candidates.items()}
    bindings[str(Path(__file__).resolve())]=file_hash(__file__)
    data=dict(version='research196-cost-sections',selection_reads_acceptance_grades=False,model_calls=0,
        prepared=str(prepared.resolve()),execution=str(execution.resolve()),runs=runs,groups=GROUPS,sections=sections,candidates=candidates,source_bindings=bindings,
        scope='Completed prefixes only; no response/proposal from an over-budget or unknown-cost call receives budget credit. Natural early stops remain visible. Cost-based cuts are descriptive, not randomized equal-wall reruns.')
    dump(out/'registration.json',data);dump(out/'seal.json',dict(sha256=file_hash(out/'registration.json')))
    print(dict(registered=len(runs),sections=len(sections),candidates={c:len(v) for c,v in candidates.items()}),flush=True)


def validate(out):
    out=Path(out);r=read(out/'registration.json')
    if file_hash(out/'registration.json')!=read(out/'seal.json')['sha256']:raise ValueError('cost_registration_changed')
    for p,h in r['source_bindings'].items():
        if file_hash(p)!=h:raise ValueError('bound_cost_source_changed:'+p)
    return r


def evaluate(out,acceptance):
    from research196_independent import runtime
    out,acceptance=Path(out),Path(acceptance);reg=validate(out)
    if read(acceptance/'outcome.json')['status']!='completed':raise ValueError('acceptance_incomplete')
    if (out/'evaluation_started.json').exists():raise ValueError('no_automatic_retry')
    dump(out/'evaluation_started.json',dict(model_calls=0,registration_sha256=file_hash(out/'registration.json')))
    adapter=runtime(Path(reg['prepared'])/'acceptance_registration.json').cases
    plans=read(acceptance/'plan.json');index={};physical=[]
    for cid,versions in reg['candidates'].items():
        mapping=read(acceptance/cid/'version_mapping.json');known=mapping['keys'];missing=[h for h in versions if h not in known]
        for h in set(versions)&set(known):
            for fault in plans[cid]['faults']:
                p=acceptance/cid/fault/f'projection{known.index(h)}.json'
                index[cid+'/'+h+'/'+fault]=dict(path=str(p.resolve()),sha256=file_hash(p),physical_reuse=True)
        if not missing:continue
        combined,labels=combine_candidates([versions[h] for h in missing])
        for fault in plans[cid]['faults']:
            m=adapter.evaluate(cid,combined,out/'native'/cid/fault,queries=plans[cid]['queries'],split='independent',fault=fault,_trusted_bundle=True)
            physical.append(dict(case_id=cid,fault=fault,**m['cost']))
            for n,h in enumerate(missing):
                projected=project_measurement(m,versions[h],labels,n);projected.update(temporal_detection(projected))
                p=out/'native'/cid/fault/f'projection{n}.json';dump(p,projected)
                index[cid+'/'+h+'/'+fault]=dict(path=str(p.resolve()),sha256=file_hash(p),physical_reuse=False)
            dump(out/'physical_cost.json',physical);print('COST_NATIVE',cid,fault,len(missing),flush=True)
    dump(out/'projection_index.json',index);dump(out/'physical_cost.json',physical)
    dump(out/'evaluation_outcome.json',dict(status='completed',model_calls=0,new_native_jobs=sum(c['native_execution_attempts'] for c in physical),acceptance=str(acceptance.resolve())))


def analyze(out):
    out=Path(out);reg=validate(out);done=read(out/'evaluation_outcome.json')
    if done['status']!='completed':raise ValueError('cost_evaluation_incomplete')
    plans=read(Path(done['acceptance'])/'plan.json');index=read(out/'projection_index.json');cache={};cells=[]
    def get(cid,h,fault):
        key=cid+'/'+h+'/'+fault
        if key not in cache:
            src=index[key]
            if file_hash(src['path'])!=src['sha256']:raise ValueError('cost_projection_changed')
            cache[key]=read(src['path'])
        return cache[key]
    for section in reg['sections']:
        faults=[]
        for fault in plans[section['case_id']]['faults']:
            measurements={a:get(section['case_id'],p['candidate_sha256'],fault) for a,p in section['checkpoints'].items()}
            targets=[set(m['targets']) for m in measurements.values()];reasons=[]
            if any(not m['native_complete'] or not m['reference_complete'] or m['critical_unknown'] for m in measurements.values()):reasons.append('unknown_or_incomplete')
            if not all(targets):reasons.append('unexposed')
            if any(t!=targets[0] for t in targets):reasons.append('target_mismatch')
            item=dict(fault=fault,eligible=not reasons,reasons=reasons)
            if not reasons:item['metrics']={a:dict(transaction_rate=len(m['transaction_detected_ids'])/len(m['targets']),timely_rate=len(m['detected_ids'])/len(m['targets']),legal_fp_records=len(m['false_positives'])) for a,m in measurements.items()}
            faults.append(item)
        cells.append(dict(**section,faults=faults))
    summaries=[]
    keys=sorted({(s['group'],s['axis'],s['budget_label']) for s in cells})
    for group,axis,budget_label in keys:
        subset=[s for s in cells if (s['group'],s['axis'],s['budget_label'])==(group,axis,budget_label)];parents=[]
        for cid in sorted({s['case_id'] for s in subset}):
            pair=[s for s in subset if s['case_id']==cid]
            if len(pair)!=2:continue
            common_faults=set.intersection(*({f['fault'] for f in s['faults'] if f['eligible']} for s in pair))
            if not common_faults:continue
            metrics={a:{k:statistics.mean(f['metrics'][a][k] for s in pair for f in s['faults'] if f['fault'] in common_faults) for k in ('transaction_rate','timely_rate','legal_fp_records')} for a in GROUPS[group]}
            parents.append(dict(case_id=cid,faults=sorted(common_faults),supported=all(s['common_observed_support'] for s in pair),metrics=metrics))
        for arm in GROUPS[group]:
            summaries.append(dict(group=group,axis=axis,budget_label=budget_label,arm=arm,paired_parents=len(parents),supported_parents=sum(p['supported'] for p in parents),
                **{k:statistics.mean(p['metrics'][arm][k] for p in parents) if parents else None for k in ('transaction_rate','timely_rate','legal_fp_records')}))
    dump(out/'analysis.json',dict(status='completed',cells=cells,summary=summaries,model_calls=0,
        scope='Same eligible faults in both seeds and every arm, then equal weights per parent. All unknown/unexposed exclusions retained. Checkpoints selected from cost only before any R196 acceptance inputs existed.'))
    print(dict(cost_sections=len(cells),summary_rows=len(summaries)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','evaluate','analyze']);p.add_argument('--prepared',type=Path);p.add_argument('--execution',type=Path);p.add_argument('--acceptance',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.action=='register':register(a.prepared,a.execution,a.out)
    elif a.action=='evaluate':evaluate(a.out,a.acceptance)
    else:analyze(a.out)
