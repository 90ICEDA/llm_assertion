"""Seal R196 paired requests and exact development-derived continuation code."""
import argparse
import ast
from pathlib import Path
import research194_refinement_runner as common
from research196_component_guard import runtime
from research196_prepare import CASES,SEEDS,verify as verify_acquisitions
import research196_cases as cases


def adapter_runtime():
    core,runner=runtime();runner.cases=cases
    return core,runner


def source_bindings():
    bindings=common.source_bindings()
    pending=[Path(__file__),Path(__file__).with_name('research196_execute.py'),Path(__file__).with_name('research196_independent.py')]
    visited=set()
    while pending:
        p=pending.pop()
        if p in visited:continue
        visited.add(p);bindings[str(p)]=common.file_hash(p)
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
            for name in names:
                if name and name.startswith('research'):
                    dep=p.with_name(name+'.py')
                    if dep.is_file():pending.append(dep)
    return bindings


def prepare(acquisitions,out):
    acquisitions=Path(acquisitions).resolve();out=Path(out).resolve()
    paid=verify_acquisitions(acquisitions)
    if common.read(acquisitions/'outcome.json')['queries']!=32:raise ValueError('first_acquisitions_incomplete')
    out.mkdir(parents=True,exist_ok=False);entries=[]
    for cid in CASES:
        base=common.read(paid['baselines'][cid])
        for seed in SEEDS:
            for search,strategy in common.r.TRAJECTORIES:
                core,runner=adapter_runtime();adapter=runner.CaseAdapter(cid)
                baseline=runner.bind_measurement(base['measurement'],adapter.case['initial'])
                record=common.read(acquisitions/'sessions'/cid/str(seed)/search/'query00/acquisition.json')
                current=runner.merge_measurements(adapter.case['initial'],[baseline,record['measurement']])
                identity=f'{cid}/{seed}/{search}_{strategy}'
                prep=runner.prepare_first(adapter,strategy,seed,baseline,runner.query_union(base['queries'],record['queries']),record,out/identity,
                    max_rounds=2,current_measurement=current)
                blocked=bool(current['critical_unknown'] or not current['native_complete'] or not current['reference_complete'])
                entries.append(dict(id=identity,case_id=cid,seed=seed,search=search,strategy=strategy,mode='blocked_unknown' if blocked else 'ready',**prep))
    protocol=common.seal_package(out,entries,list(CASES),maximum_rounds=2)
    protocol.update(version='research196',seeds=list(SEEDS),workers=2,acquisitions=str(acquisitions),
        authorization='NOT AUTHORIZED. New R196 seal-bound user authorization required; earlier grants do not apply.',
        common_component_guard=True,history_gate='R0-R3 retain their registered differences; component activity guard common to every arm.',
        wall_budget_per_search_unit=120,cost_models=paid['cost_models'],
        general_window_and_multi_inflight_scope='Native synthetic interface qualification separate; not claimed as these four RTL model experiments.',
        independent_protocol='All 64 versions frozen before two new inputs per case/seed and new reserved mutation sites. No independent data in prompts.',
        source_bindings={**protocol['source_bindings'],**source_bindings(),str(acquisitions/'protocol.json'):common.file_hash(acquisitions/'protocol.json')})
    common.dump(out/'protocol.json',protocol)
    from research196_independent import register
    register(out)
    protocol['source_bindings'][str(out/'acceptance_registration.json')]=common.file_hash(out/'acceptance_registration.json')
    common.dump(out/'protocol.json',protocol);common.dump(out/'seal.json',dict(version='research196',protocol_sha256=common.file_hash(out/'protocol.json')))
    review=dict(population=64,callable_first_requests=sum(e['mode']=='ready' for e in entries),blocked_initial=sum(e['mode']=='blocked_unknown' for e in entries),
        maximum_model_calls=protocol['maximum_model_calls'],max_rounds=2,new_model_calls=0,
        callable_request_bytes=sum(Path(e['request']).stat().st_size for e in entries if e['mode']=='ready'),
        protocol=str(out/'protocol.json'),request_manifest=entries)
    common.dump(out/'review.json',review);verify(out);print({k:v for k,v in review.items() if k!='request_manifest'},flush=True)


def verify(prepared):
    p,seal=common.verify_package(prepared)
    if p['version']!='research196' or len(p['entries'])!=64 or p['max_rounds']!=2 or p['maximum_model_calls']>128:raise ValueError('R196_protocol_configuration')
    verify_acquisitions(p['acquisitions'])
    for e in p['entries']:
        core,runner=adapter_runtime();a=runner.CaseAdapter(e['case_id']);s=common.read(e['state'])
        ctl=runner.controller_from(a,e['strategy'],s['baseline'],2);ctl.consider_empty_domain(s['first_measurement'])
        if core.build_request(a.case,ctl,s['public_evidence'],e['seed'],0)!=common.read(e['request']):raise ValueError('first_request_reconstruction_mismatch')
    return p,seal


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify']);p.add_argument('--acquisitions',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();prepare(a.acquisitions,a.out) if a.action=='prepare' else print(verify(a.out)[1])
