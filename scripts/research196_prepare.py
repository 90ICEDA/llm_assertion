"""Prepare paid first acquisitions for a new paired S/R/A experiment; no model."""
import argparse
from pathlib import Path
import random
from research194_refinement_runner import ROOT,read,dump,file_hash,source_bindings
from research194_refinement import digest
import research196_cases as cases
from research196_active_search import Session,fit_wall_cost

CASES=('arbiter','counter','uart','ibex_flush')
SEEDS=(19607,19619)


def prepare(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    old194=ROOT/'deliverables/research194_active_native_20261103_r02'
    old195=ROOT/'deliverables/research195_active_native_20261103_r01'
    baseline_index=read(old194/'baseline_index.json');models={};calibration={};baselines={}
    bindings=source_bindings()
    for n in ('research196_prepare.py','research196_cases.py','research196_active_search.py','research196_component_guard.py','research195_active_queries.py','research195_refinement_adapter.py','research194_refinement_safe_localization.py'):
        p=ROOT/'scripts'/n;bindings[str(p)]=file_hash(p)
    for cid in CASES:
        paths=sorted((old195/'calibration'/cid).glob('n*/acquisition.json')) if cid in ('arbiter','counter') else sorted((old194/'sessions'/cid).glob('*/S0/query*/acquisition.json'))
        records=[read(p) for p in paths];models[cid]=fit_wall_cost(records)
        calibration[cid]=[dict(path=str(p),sha256=file_hash(p)) for p in paths]
        bindings.update({str(p):file_hash(p) for p in paths})
        baselines[cid]=baseline_index[cid+'/19407'];bindings[baselines[cid]]=file_hash(baselines[cid])
        for source in cases.get_case(cid)['sources']:
            p=ROOT/source;bindings[str(p)]=file_hash(p)
    units=[dict(case_id=c,seed=s,strategy=a) for c in CASES for s in SEEDS for a in ('S0','S1','S2','S3')]
    random.Random(19600).shuffle(units)
    pools={f'{c}/{s}':cases.query_pool(c,seed=s) for c in CASES for s in SEEDS}
    protocol=dict(version='research196',cases=list(CASES),seeds=list(SEEDS),run_order=units,
        cost_models=models,calibration=calibration,baselines=baselines,query_pools=pools,source_bindings=bindings,
        queries_per_search_unit=2,wall_budget_per_search_unit=120,first_acquisition_queries=32,first_acquisition_native_jobs=64,
        model_calls=0,independent_results_read=False,
        scope='New registered first-query acquisition. Historical development timing calibrates cost; no old independent grades train selection. Public baselines are reused, with physical cost zero and source acquisition cost retained.',
        planned_model_population=dict(cases=4,seeds=2,arms=8,round_ceiling=2,maximum_calls_before_unknown_exclusions=128),
        primary_cost='Actual acquisition plus planning minus explicit scheduling lock wait; no partial/over-budget query credit.')
    dump(out/'protocol.json',protocol);dump(out/'seal.json',dict(protocol_sha256=file_hash(out/'protocol.json')))
    print(dict(prepared=str(out),models=models),flush=True)


def verify(out):
    out=Path(out);p=read(out/'protocol.json')
    if read(out/'seal.json')['protocol_sha256']!=file_hash(out/'protocol.json'):raise ValueError('protocol_changed')
    for path,h in p['source_bindings'].items():
        if file_hash(path)!=h:raise ValueError('source_or_calibration_changed:'+path)
    return p


def acquire(out):
    out=Path(out).resolve();p=verify(out);progress=[]
    if (out/'started.json').exists():raise ValueError('no_automatic_restart')
    dump(out/'started.json',dict(model_calls=0))
    for unit in p['run_order']:
        verify(out);cid=unit['case_id'];seed=unit['seed'];strategy=unit['strategy']
        baseline=read(p['baselines'][cid]);folder=out/'sessions'/cid/str(seed)/strategy
        session=Session(cid,strategy,seed,folder,initial_queries=baseline['queries'],initial_evidence=baseline['measurement']['evidence'],
            max_queries=p['queries_per_search_unit'],adapter=cases,cost_model=p['cost_models'][cid],wall_budget=p['wall_budget_per_search_unit'])
        if digest(session.pool)!=digest(p['query_pools'][f'{cid}/{seed}']):raise ValueError('query_pool_changed')
        record=session.acquire(cases.get_case(cid)['initial'])
        if record is None:raise ValueError('initial_budget_cannot_fit_any_registered_query')
        progress.append(dict(**unit,path=str(folder/'query00/acquisition.json'),sha256=file_hash(folder/'query00/acquisition.json'),
            unknown=len(record['measurement']['critical_unknown']),native_complete=record['measurement']['native_complete'],cost=record['cost']))
        dump(out/'progress.json',progress);print('FIRST',cid,seed,strategy,'unknown',progress[-1]['unknown'],flush=True)
    verify(out);dump(out/'outcome.json',dict(status='all_first_acquisitions_completed',queries=len(progress),model_calls=0,
        native_jobs=sum(x['cost']['native_execution_attempts'] for x in progress)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','acquire']);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();(prepare if a.action=='prepare' else acquire)(a.out)
