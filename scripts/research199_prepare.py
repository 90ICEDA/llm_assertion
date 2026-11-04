"""48 sealed first requests; future requests depend only on actual dev results."""
import argparse
import ast
import json
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash,merge_measurements,query_union,ENDPOINT
from research199_refinement import runtime,ARMS
from research199_independent import register
import research197_cases as cases

def sources(previous):
    result=dict(previous['source_bindings']);pending=list((ROOT/'scripts').glob('research199_*.py'))
    while pending:
        p=pending.pop().resolve()
        if str(p) in result:continue
        result[str(p)]=file_hash(p)
        for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            mods=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module] if isinstance(n,ast.ImportFrom) else []
            for m in mods:
                if m and m.startswith('research') and p.with_name(m+'.py').is_file():pending.append(p.with_name(m+'.py'))
    return result

def prepare(acquisition,qualification,out):
    acquisition=Path(acquisition).resolve();out=Path(out).resolve();qualification=Path(qualification).resolve()
    acq=read(acquisition/'outcome.json')
    if acq['status']!='complete' or read(qualification/'outcome.json')['status']!='qualified':raise ValueError('local_qualification_required')
    previous=ROOT/'deliverables/research198_refinement_prepare_20261104_r01'
    from research198_prepare import verify as old_verify
    old=old_verify(previous);out.mkdir(parents=True,exist_ok=False);entries=[]
    for cid in cases.IDS:
        for seed in old['seeds']:
            source_entry=next(e for e in old['entries'] if e['case_id']==cid and e['seed']==seed and e['search']=='S3' and e['policy']=='local_first')
            fixed=read(source_entry['state'])
            for arm,spec in ARMS.items():
                if spec['cohort']=='factorial':
                    baseline=fixed['baseline'];queries=fixed['queries'];first=fixed['first_acquisition'];measurement=fixed['first_measurement'];source=source_entry['state']
                else:
                    row=next(v for v in acq['entries'] if v['case_id']==cid and v['seed']==seed and v['search']==spec['search'])
                    first=read(row['path']);b=read(row['baseline']);baseline=b['measurement'];queries=query_union(b['queries'],first['queries'])
                    measurement=merge_measurements(cases.get_case(cid)['initial'],[baseline,first['measurement']]);source=row['path']
                identity=f'{cid}/{seed}/{arm}';core,runner=runtime(arm);adapter=cases.CaseAdapter(cid)
                prep=runner.prepare_first(adapter,spec['strategy'],seed,baseline,queries,first,out/'requests'/identity,max_rounds=3,current_measurement=measurement)
                ctx=json.loads(read(prep['request'])['messages'][-1]['content']);contract=ctx['output_contract']
                stage='free' if spec['strategy']=='R1' else 'local' if isinstance(contract.get('operations'),dict) else 'compose'
                blocked=bool(measurement['critical_unknown'] or not measurement['native_complete'] or not measurement['reference_complete'])
                entries.append(dict(id=identity,case_id=cid,seed=seed,arm=arm,**spec,mode='blocked_unknown' if blocked else 'ready',max_rounds=3,first_stage=stage,
                    source_state=str(source),source_state_sha256=file_hash(source),**prep))
            print('PREPARED',cid,seed,flush=True)
    p=dict(version='research199',endpoint=ENDPOINT,model=old['model'],temperature=.2,max_output_tokens=2048,timeout_seconds=300,workers=2,retries=0,
        population=len(entries),entries=entries,case_ids=list(cases.IDS),seeds=old['seeds'],maximum_model_calls=sum(e['max_rounds'] for e in entries if e['mode']=='ready'),
        acquisition=str(acquisition),acquisition_sha256=file_hash(acquisition/'outcome.json'),cost_models=acq['cost_models'],qualification=str(qualification),
        source_bindings=sources(old),authorization='NOT AUTHORIZED. Previous grants bind different versions/requests.',
        experiment='24 fixed S3 factorial trajectories (routing x contract), plus 24 genuinely online S0/S3 x feedback/local-first trajectories. Three calls per trajectory; shared native history/activity gates.',
        primary_metrics=['necessary obligation protection per parent Bug','legal false positives','transaction and timely detection','accepted effective edits','interface failures','new-evidence-to-edit-to-independent-obligation linkage'],
        primary_cost='Predeclared completed-prefix token cap 131072 per trajectory. Over-cap calls counted as spent but their proposals not credited below cap. This is a cost-section comparison, not strict equal-cost randomized execution.',
        secondary_costs=dict(token_grid=[0,65536,131072,262144],service_seconds_grid=[0,120,240,480],round_grid=[0,1,2,3],minimum_observed_total=True,
            service='Query planning + native compilation/execution + history replay + model service; exclude scheduler lock wait. Fixed cohort historical acquisitions separately archived. Online first acquisition logical costs charged to each paired arm; shared physical jobs identified.'),
        search_limits=dict(submitted_queries_per_online_trajectory=3,wall_budget_seconds=180,new_first_query_pairs=12,baseline='Same original native baseline; historical calibration estimated cost only; actual errors/costs recorded.'),
        contamination='R197/R198 independent records used only for P0. Not sent to models and not counted as fresh generalization. New held-out instances registered separately; no results read before all 48 freeze.',
        causal_scope='B arms change only route and local edit interface; localization, composition permission fix, native acceptance gates and fallback stay common. A comparison additionally changes acquisition policy.',
        fallback_scope='Observe naturally occurring confirmed failures. Schema/no-change/unknown never authorize escalation. No deliberately ineffective model repair; unobserved branches remain unobserved.',
        linkage_scope='Temporal/provenance association alone is not proof a particular evidence item caused an edit. Native before/after checks establish improvement; alternative explanations remain explicit.',
        limits=['Finite windows and unique in-flight IDs only.','No new fault-family enhancement cohort.','No guaranteed positive result or guaranteed newly protected obligation.','No full latest S0-S3 x R0-R3 matrix.'])
    register(out,p);p['source_bindings'][str(out/'acceptance_registration.json')]=file_hash(out/'acceptance_registration.json')
    p['source_bindings'][str(qualification/'outcome.json')]=file_hash(qualification/'outcome.json')
    dump(out/'protocol.json',p);dump(out/'seal.json',dict(protocol_sha256=file_hash(out/'protocol.json')))
    review=dict(population=len(entries),first_requests=sum(e['mode']=='ready' for e in entries),maximum_model_calls=p['maximum_model_calls'],model_calls=0,
        request_bytes=sum(Path(e['request']).stat().st_size for e in entries),
        first_stages={arm:{stage:sum(e['arm']==arm and e['first_stage']==stage for e in entries) for stage in ('local','compose','free')} for arm in ARMS},
        requests=[{k:e[k] for k in ('id','arm','mode','first_stage','request','request_sha256','max_rounds')} for e in entries])
    dump(out/'review.json',review);verify(out);print({k:v for k,v in review.items() if k!='requests'},flush=True)

def verify(out):
    out=Path(out);p=read(out/'protocol.json')
    if p['version']!='research199' or len(p['entries'])!=48 or p['maximum_model_calls']>144:raise ValueError('registered_population')
    if file_hash(out/'protocol.json')!=read(out/'seal.json')['protocol_sha256']:raise ValueError('seal_changed')
    for src,h in p['source_bindings'].items():
        if file_hash(src)!=h:raise ValueError('bound_source_changed:'+src)
    blocks={}
    for e in p['entries']:
        if file_hash(e['state'])!=e['state_sha256'] or file_hash(e['source_state'])!=e['source_state_sha256']:raise ValueError('prepared_state_changed')
        s=read(e['state']);core,runner=runtime(e['arm']);adapter=cases.CaseAdapter(e['case_id'])
        ctl=runner.controller_from(adapter,e['strategy'],s['baseline'],3);ctl.consider_empty_domain(s['first_measurement'])
        request=core.build_request(adapter.case,ctl,s['public_evidence'],e['seed'],0)
        if request!=read(e['request']) or core.digest(request)!=e['request_sha256']:raise ValueError('first_request_reconstruction:'+e['id'])
        key=(e['case_id'],e['seed'],e['cohort'],e['search']);info=core.digest({k:s[k] for k in ('initial','baseline','queries','first_measurement','public_evidence')})
        if key in blocks and blocks[key]!=info:raise ValueError('unequal_evidence_within_block')
        blocks[key]=info
        for src,h in s['first_measurement']['native_bindings'].items():
            if file_hash(src)!=h:raise ValueError('native_evidence_changed')
    return p

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify']);p.add_argument('--acquisition',type=Path);p.add_argument('--qualification',type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();prepare(a.acquisition,a.qualification,a.out) if a.action=='prepare' else print(verify(a.out)['maximum_model_calls'])
