"""Paid local acquisition and exact request sealing; no model/network access."""
import argparse
import ast
import copy
from pathlib import Path
import research194_refinement_runner as common
from research196_active_search import fit_wall_cost
import research197_cases as cases
from research197_search import session,SearchCases
from research197_refinement import runtime

SEEDS=(19711,19723)

def sources():
    bindings=common.source_bindings();pending=list((common.ROOT/'scripts').glob('research197_*.py'))
    pending += [common.ROOT/'scripts/research196_active_search.py',common.ROOT/'scripts/research196_component_guard.py']
    while pending:
        path=pending.pop();name=str(path.resolve())
        if name in bindings:continue
        bindings[name]=common.file_hash(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
            for module in modules:
                if module and module.startswith('research'):
                    p=path.with_name(module+'.py')
                    if p.is_file():pending.append(p)
    for cid in cases.IDS:
        for source in cases.runtime().CONFIG[cid]['sources']:
            p=common.ROOT/source;bindings[str(p.resolve())]=common.file_hash(p)
    for p in (cases.SRC/'provenance.json',cases.SRC/'commit.json',cases.SRC/'pull_request.json',cases.delta.SRC/'commit.json',cases.delta.SRC/'pull_request.json'):
        bindings[str(p.resolve())]=common.file_hash(p)
    return bindings

def prepare(qualification,local_qualification,out):
    out=Path(out).resolve();qualification=Path(qualification).resolve()
    if common.read(qualification/'outcome.json')['status']!='qualified' or common.read(Path(local_qualification)/'outcome.json')['status']!='qualified':raise ValueError('native_qualification_required')
    out.mkdir(parents=True,exist_ok=False);baselines={};models={};entries=[]
    for cid in cases.IDS:
        cfg=cases.get_case(cid);baseline=common.read(qualification/cid/'candidate0.json');queries=cases.query_pool(cid)[:2]
        bp=out/'baselines'/f'{cid}.json';common.dump(bp,dict(measurement=baseline,queries=queries));baselines[cid]=str(bp)
        # Two independently timed physical query pairs from qualification, plus
        # a third actual development run. Fit native cost and measured adapter
        # overhead separately; never calibrate on final acceptance traces.
        native=common.read(qualification/cid/'native/executions.json');cal=[]
        for q in queries:
            jobs=[j for j in native if j['query_id']==q['id']]
            seconds=sum(common.read(Path(j['folder'])/f)['wall_seconds'] for j in jobs for f in ('compile.json','execute.json'))
            cal.append(dict(query=q,cost=dict(acquisition_wall_seconds=seconds),heldout_access=False))
        q=cases.query_pool(cid)[2];m=cases.evaluate(cid,cfg['initial'],out/'calibration'/cid,queries=[q])
        if not m['native_complete'] or not m['reference_complete']:raise ValueError('calibration_unknown:'+cid)
        cal.append(dict(query=q,cost=dict(acquisition_wall_seconds=m['cost']['native_seconds']),heldout_access=False))
        model=fit_wall_cost(cal);overhead=max(0,m['cost']['wall_seconds']-m['cost']['native_seconds'])
        model['fixed_seconds']+=overhead;model['adapter_overhead_seconds']=overhead
        model['calibration_scope']='Three actual native query-pair times plus measured third-query adapter overhead; small-sample estimate, errors must be reported against actual acquisition cost.'
        models[cid]=model;common.dump(out/'cost_models.json',models)
        acquired={}
        for seed in SEEDS:
            for search in ('S0','S1','S2','S3'):
                s=session(cid,search,seed,out/'first_acquisitions'/cid/str(seed)/search,baseline=baseline,queries=queries,cost_model=model,max_queries=3)
                record=s.acquire(cfg['initial'],round=0)
                if record is None:raise ValueError('initial_budget_stop')
                acquired[(seed,search)]=record;print('ACQUIRED',cid,seed,search,len(record['new_gap_ids']),flush=True)
        for seed in SEEDS:
            registrations=[dict(search=s,strategy=r,arm=None,max_rounds=3,tag=s+'_'+r) for s,r in common.r.TRAJECTORIES]
            registrations += [dict(search='S0',strategy='R3',arm=arm,max_rounds=1,tag=arm) for arm in ('F','P','T')]
            for registration in registrations:
                e=registration;core,runner=runtime(e['arm']);adapter=cases.CaseAdapter(cid);a=acquired[(seed,e['search'])]
                current=common.merge_measurements(cfg['initial'],[baseline,a['measurement']]);identity=f"{cid}/{seed}/{e['tag']}"
                prep=runner.prepare_first(adapter,e['strategy'],seed,baseline,common.query_union(queries,a['queries']),a,out/'requests'/identity,
                    max_rounds=e['max_rounds'],current_measurement=current)
                blocked=bool(current['critical_unknown'] or not current['native_complete'] or not current['reference_complete'])
                entries.append(dict(id=identity,case_id=cid,seed=seed,mode='blocked_unknown' if blocked else 'ready',**e,**prep))
        common.dump(out/'entries.progress.json',entries)
    p=dict(version='research197',endpoint=common.ENDPOINT,model='deepseek/deepseek-v3-0324',temperature=.2,max_output_tokens=2048,timeout_seconds=300,
       workers=2,retries=0,case_ids=list(cases.IDS),seeds=list(SEEDS),entries=entries,baselines=baselines,cost_models=models,
       maximum_model_calls=sum(e['max_rounds'] for e in entries if e['mode']=='ready'),population=len(entries),maximum_population_model_calls=162,
       main_round_ceiling=3,isolated_round_ceiling=1,wall_budget_per_search_unit=180,
       authorization='NOT AUTHORIZED. Earlier research194/195/196 grants do not cover this package.',
       external_payload='Original before/after or upstream RTL, specification, candidate SVA, confirmed development waveforms and per-round feedback. No reserved fault catalogue or acceptance inputs/results.',
       qualification=str(qualification),local_qualification=str(Path(local_qualification).resolve()),
       source_bindings=sources(),limits=['Finite 1..32 sampled window compilation; not arbitrary SVA sequences.','ID scenarios use unique in-flight IDs and bounded 1..8 response age; not arbitrary unbounded transactions.',
         'Three rounds allow but do not force a real model to traverse every fallback branch. Handwritten fallback qualification stays separately labelled.'])
    from research197_independent import register
    register(out,p);p['source_bindings'][str(out/'acceptance_registration.json')]=common.file_hash(out/'acceptance_registration.json')
    common.dump(out/'protocol.json',p);common.dump(out/'seal.json',dict(protocol_sha256=common.file_hash(out/'protocol.json')))
    review=dict(population=len(entries),main_trajectories=sum(e['arm'] is None for e in entries),isolated_trajectories=sum(e['arm'] is not None for e in entries),
       callable_first_requests=sum(e['mode']=='ready' for e in entries),blocked_initial=sum(e['mode']!='ready' for e in entries),maximum_model_calls=p['maximum_model_calls'],model_calls=0,
       first_request_bytes=sum(Path(e['request']).stat().st_size for e in entries),requests=[{k:e[k] for k in ('id','mode','request','request_sha256','max_rounds')} for e in entries])
    common.dump(out/'review.json',review);verify(out);print({k:v for k,v in review.items() if k!='requests'},flush=True)

def verify(out):
    out=Path(out);p=common.read(out/'protocol.json')
    if p['version']!='research197' or len(p['entries'])!=66 or p['maximum_model_calls']>162:raise ValueError('population')
    if common.file_hash(out/'protocol.json')!=common.read(out/'seal.json')['protocol_sha256']:raise ValueError('protocol_seal')
    for path,h in p['source_bindings'].items():
        if common.file_hash(path)!=h:raise ValueError('source_binding:'+path)
    for e in p['entries']:
        if common.file_hash(e['state'])!=e['state_sha256'] or common.r.digest(common.read(e['request']))!=e['request_sha256']:raise ValueError('first_request_binding:'+e['id'])
        state=common.read(e['state']);core,runner=runtime(e['arm']);adapter=cases.CaseAdapter(e['case_id'])
        controller=runner.controller_from(adapter,e['strategy'],state['baseline'],e['max_rounds']);controller.consider_empty_domain(state['first_measurement'])
        if core.build_request(adapter.case,controller,state['public_evidence'],e['seed'],0)!=common.read(e['request']):raise ValueError('request_reconstruction:'+e['id'])
        for path,h in state['first_measurement']['native_bindings'].items():
            if common.file_hash(path)!=h:raise ValueError('native_binding:'+path)
    return p

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','verify']);ap.add_argument('--qualification',type=Path);ap.add_argument('--local-qualification',type=Path);ap.add_argument('--out',required=True,type=Path)
    a=ap.parse_args();prepare(a.qualification,a.local_qualification,a.out) if a.action=='prepare' else print(verify(a.out)['maximum_model_calls'])
