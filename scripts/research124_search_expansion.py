"""Presealed all-eligible-candidate parameter expansion. No model/test input access.

Each worker owns one candidate/configuration directory and its own Python process.
Existing metered query helpers patch globals, so threads must NOT run queries.
"""
import argparse
import concurrent.futures
import copy
import json
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import research117_search_preparation as s

b, policy = s.b, s.previous.policy
ROOT, read, dump, sha = b.ROOT, b.read, b.dump, b.digest
SOURCE = ROOT / 'deliverables/research117_search_prepare_20261025_r01'
MATRIX = ROOT / 'deliverables/research122_discrimination_audit_20261025_r01'
CONFIGS = ((2, 1), (4, 2))
SEEDS = (12407, 12419)
METHODS = s.METHODS
BUDGET = 3
MODES = s.previous.MODES


def prepare(out):
    b.verify(SOURCE)
    for n, h in read(MATRIX / 'sealed.json').items(): assert sha(MATRIX / n) == h, n
    inventory = read(MATRIX / 'search_candidates.json')
    included = [c for c in inventory if c['qualified']]
    assert len(included) == 8 and len(inventory) == 9
    out.mkdir(parents=True, exist_ok=False)
    (out / 'candidates').mkdir()
    for name in [c['name'] for c in included] + ['reference']:
        shutil.copy2(SOURCE / 'candidates' / (name + '.json'), out / 'candidates' / (name + '.json'))
    shutil.copy2(SOURCE / 'axis_fifo.v', out / 'axis_fifo.v')
    assert sha(out / 'axis_fifo.v') == sha(b.extension.runtime.RTL)
    dump(out / 'inventory.json', inventory)
    registry = b.historical_registry(); known = set(registry['keys'])
    sources = registry['sources']
    for directory in ('research82_search_20261025_r01', 'research84_generalization_20261025_r01', SOURCE.name):
        folder = ROOT / 'deliverables' / directory
        for filename in ('records.json', 'public_feedback.json'):
            f = folder / filename
            value = read(f)
            records = value if isinstance(value, list) else [r for v in value.values() for r in v['results']]
            known.update(k for r in records for k in r['gap_keys'])
            sources.append(dict(path=f.relative_to(ROOT).as_posix(), sha256=sha(f)))
    dump(out / 'known_development.json', dict(keys=sorted(known), sources=sources,
        mechanisms=sorted({'/'.join(k.split('/')[1:]) for k in known}),
        completeness='Partial development registry. Missing entry means previously unregistered, not globally novel.',
        policy_use='Reporting only. Every policy sees same common public runs and then its own permitted feedback. Registry is never passed to selectors.'))
    shutil.copy2(MATRIX / 'search_gap_registry.json', out / 'current_misses.json')
    dump(out / 'protocol.json', dict(name='research124_all_eligible_parameter_search', configs=CONFIGS,
        seeds=SEEDS, methods=METHODS, budget=BUDGET, modes=MODES, workers=4,
        included=[c['name'] for c in included], excluded=[dict(name=c['name'], reason=c['failure']) for c in inventory if not c['qualified']],
        population='All8 research122 publicly qualified archived candidates, no favorable-outcome selection. c07 stays in original9 denominator. No new parent or new independent assertion acceptance.',
        qualification='Per parameter: both native builds pass, both public queries healthy, correct RTL/reference legal and zero candidate/reference native false alarms. At least one confirmed first target violation must be exposed; absence is ineligible_no_exposure, not success. Miss count never selects candidates.',
        common_public=[dict(seed=12400, family='overlap', duration=None),dict(seed=12401, family='backpressure', duration=1)],
        exposure='Persist counts per fault and obligation from independent first-violation rows, including unexposed modes and excluded later attribution. No requirement or claim every obligation is exposed by qualification.',
        information='Unchanged research65 selectors and per-method permitted views. Two complete candidates used for actual whole-set XOR. Same RTL/spec/mode access, public evidence, seeds and per-query stimuli formula for all methods. Known registry used only after measurement for reporting.',
        scoring='Subtract current common public keys for public-unexposed discovery; separately subtract all sealed known-development keys including research117. Parameter/seed/cycle/waveform variants do not create new candidate+obligation+mechanism discoveries.',
        dedup='candidate content hash/FN|FP/obligation/mechanism, long_ variants collapsed. Report pooled mechanisms without candidate separately; candidate counts are not Bug counts.',
        budget_scope='3 queries per eligible candidate/configuration/seed/method, 20 native replays/query. Unknown consumes budget. No extension, retry, outcome-based reselection or selector adjustment.',
        maximum_search_queries=576, maximum_public_queries=32, maximum_query_native_executions=12160,
        cost='Fresh executes, shared native builds per configuration; no query result cache. Record compile/smoke command cost, each execute, reference/sampling/judgement time, selection/query time and first-discovery cost. Reference time nested in query time, never add twice.',
        scheduling='Four isolated processes, one candidate/config per worker. Method order rotates by sealed task/seed index. Query and wall times under contention descriptive, not causal speed proof. Counts are primary cost measure.',
        stopping='Native compile/public failure excludes only that parameter task with reason. Infrastructure exception stops dispatch/active tasks at query boundary; partial artifacts and budget retained. No automatic rerun.',
        scope='Actual axis_fifo plus previously defined artificial faults; finite simulation, no formal proof, no new SVA/model generation. Prior independent test inputs/results not read.', model_calls=0, formal_calls=0))
    checks = policy.tests()
    for seed in SEEDS:
        for method in METHODS:
            p = policy.factory(method, seed)
            assert policy.decision(p,method,seed,0,[])['family'] in policy.TARGETS
            checks.append(str(seed) + '/' + method)
    dump(out / 'preflight.json', dict(passed=True, checks=checks, count=len(checks)))
    dump(out / 'code_versions.json', {p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT / 'scripts').glob('*.py')})
    dump(out / 'sealed.json', {p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    dump(out / 'outcome.json', dict(status='prepared', model_calls=0))
    print('SEALED124', len(included), 'candidates', CONFIGS, 'maximum576 queries', flush=True)


def exposure(folder):
    result = {}
    for mode in MODES[1:]:
        value = read(folder / 'judgements' / (mode + '.json'))
        info = b.loop.inspect(value['target_rows'])
        result[mode] = dict(first_violation_rows=len(value['target_rows']),
            obligations=dict(Counter(r['obligation'] for r in value['target_rows'])),
            detections=len(info['detections']), misses=len(info['misses']), critical_unknown=len(value['unknown_rows']),
            later_unknown=len(value['exclusions']))
    return result


def work(args):
    root_s, name, depth, pipeline, index = args
    root = Path(root_s); task = root / 'tasks' / f'd{depth}_p{pipeline}' / name
    calls=[]; records=[]; public=[]; costs=[]; start=time.time()
    try:
        task.mkdir(parents=True, exist_ok=False)
        (task / 'candidates').mkdir()
        cs = {n:read(root / 'candidates' / (n+'.json')) for n in (name,'reference')}
        for n in cs: dump(task / 'candidates' / (n+'.json'),cs[n])
        dump(task / 'code_versions.json', read(root / 'code_versions.json'))
        dump(task / 'sealed.json', {p.relative_to(task).as_posix():sha(p) for p in task.rglob('*') if p.is_file()})
        builds = {n:read(root / 'builds' / f'd{depth}_p{pipeline}' / n / 'compiled.json') for n in cs}
        pair = name+'__reference'
        with b.extension.installed(), patch.object(b,'MODES',MODES):
            def query(folder, context):
                if (root / 'STOP.json').exists(): raise RuntimeError('global_infrastructure_stop')
                r=b.query(folder,builds,cs,(name,'reference'),b.schedule(context['stimulus_seed'],context['family'],context['duration']),context,calls)
                dump(folder/'exposure.json',exposure(folder))
                for n in cs:
                    for mode in MODES:
                        f=folder/n/mode/'execute.json'
                        costs.append(dict(path=f.relative_to(ROOT).as_posix(),record=read(f)))
                return r
            compiled=all(v['native']['compile_status']=='passed' for v in builds.values())
            if compiled:
                for q,(family,duration) in enumerate((('overlap',None),('backpressure',1))):
                    public.append(query(task/'public'/pair/f'q{q}',dict(pair=pair,stage='public',method='common',seed=0,query=q,
                        family=family,duration=duration,stimulus_seed=12400+q)))
            health=compiled and len(public)==2 and all(r['healthy'] and all(r['correct_accepts'].values()) for r in public)
            exposed=sum(v['first_violation_rows'] for q in range(len(public)) for v in read(task/'public'/pair/f'q{q}/exposure.json').values())
            qualified=bool(health and exposed>0)
            reasons=[]
            if not compiled: reasons.append('compile_failure')
            if compiled and not health: reasons.append('public_native_reference_or_false_alarm_failure')
            if not exposed: reasons.append('no_confirmed_target_exposure')
            dump(task/'qualification.json',dict(name=name,depth=depth,pipeline=pipeline,qualified=qualified,reasons=reasons,
                first_violation_observations=exposed,public_queries=len(public)))
            pubkeys=sorted({k for r in public for k in r['gap_keys']})
            dump(task/'public_feedback.json',{pair:dict(results=public,gap_keys=pubkeys)})
            dump(task/'public_freeze.json',dict(sha256=sha(task/'public_feedback.json'),at=time.time()))
            print('QUALIFY124',depth,pipeline,name,qualified,reasons,flush=True)
            known=set(read(root/'known_development.json')['keys'])
            if qualified:
                for si,seed in enumerate(SEEDS):
                    offset=(index+si)%len(METHODS); order=METHODS[offset:]+METHODS[:offset]
                    for method in order:
                        p=policy.factory(method,seed);history=[];seen=set(pubkeys)
                        for r in public:history.append(policy.update(p,method,r['family'],r))
                        for q in range(BUDGET):
                            folder=task/'queries'/pair/f's{seed}'/method/f'q{q}'
                            t=time.perf_counter();chosen=policy.decision(p,method,seed,q,history);dt=time.perf_counter()-t
                            dump(folder/'selection.json',dict(chosen=chosen,permitted_history=history))
                            r=query(folder,dict(pair=pair,stage='search',method=method,seed=seed,query=q,
                                family=chosen['family'],duration=chosen.get('duration'),stimulus_seed=seed*100+q))
                            r.update(public_unexposed_keys=sorted(set(r['gap_keys'])-set(pubkeys)),
                                first_new_keys=sorted(set(r['gap_keys'])-seen),previously_unregistered_keys=sorted(set(r['gap_keys'])-known),selector_seconds=dt)
                            seen.update(r['gap_keys']);history.append(policy.update(p,method,r['family'],r))
                            dump(folder/'result.json',r);records.append(r)
                            dump(task/'records.json',records)
                        print('SEARCH124',depth,pipeline,name,seed,method,len(records),flush=True)
            dump(task/'outcome.json',dict(status='completed',qualified=qualified,search_queries=len(records),elapsed_seconds=time.time()-start))
        return task.relative_to(root).as_posix()
    except BaseException as exc:
        dump(root/'STOP.json',dict(task=str(task),error=repr(exc)))
        dump(task/'outcome.json',dict(status='interrupted',error=repr(exc),search_queries=len(records)))
        raise
    finally:
        dump(task/'records.json',records);dump(task/'reference_costs.json',calls);dump(task/'execute_costs.json',costs)


def build_one(args):
    root_s,name,depth,pipeline=args;root=Path(root_s)
    with b.extension.installed():
        c=read(root/'candidates'/(name+'.json'))
        compiled=b.loop.runtime.build(c,root/'builds'/f'd{depth}_p{pipeline}'/name,depth,pipeline)
    print('BUILD124',depth,pipeline,name,compiled['native']['compile_status'],flush=True)
    return name,depth,pipeline


def run(root):
    b.verify(root); assert read(root/'outcome.json')['status']=='prepared'
    assert sha(root/'axis_fifo.v')==sha(b.extension.runtime.RTL)
    protocol=read(root/'protocol.json');names=protocol['included'];start=time.time()
    dump(root/'outcome.json',dict(status='running',started=start))
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            list(pool.map(build_one,[(str(root),n,d,p) for d,p in CONFIGS for n in names+['reference']]))
            tasks=list(pool.map(work,[(str(root),n,d,p,i) for i,(d,p,n) in enumerate((d,p,n) for d,p in CONFIGS for n in names)]))
        b.verify(root)
        outcomes=[read(root/t/'outcome.json') for t in tasks]
        dump(root/'outcome.json',dict(status='completed',tasks=tasks,qualified=sum(o['qualified'] for o in outcomes),
            search_queries=sum(o['search_queries'] for o in outcomes),elapsed_seconds=time.time()-start,model_calls=0,formal_calls=0))
        print('COMPLETE124',read(root/'outcome.json'),flush=True)
    except BaseException as exc:
        dump(root/'outcome.json',dict(status='interrupted',error=repr(exc),elapsed_seconds=time.time()-start));raise


def audit_one(args):
    task_s,out_s=args
    with b.extension.installed(),patch.object(b,'MODES',MODES):
        s.previous.raw.audit(Path(task_s),Path(out_s))


def audit_run(root,out):
    b.verify(root);state=read(root/'outcome.json');assert state['status']=='completed'
    out.mkdir(parents=True,exist_ok=False)
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(audit_one,[(str(root/t),str(out/t)) for t in state['tasks']]))
    values=[read(out/t/'audit.json') for t in state['tasks']]
    dump(out/'audit.json',dict(passed=all(v['passed'] for v in values),tasks=len(values),
        native_replays_verified=sum(v['native_replays_verified'] for v in values),
        reference_wall_seconds=sum(v['reference_wall_seconds'] for v in values),
        model_calls=0,new_native_executions=0,source_seal=sha(root/'sealed.json')))
    print('AUDIT124',read(out/'audit.json'),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','run','audit'])
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--audit-out',type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='run':run(a.out.resolve())
    else:audit_run(a.out.resolve(),a.audit_out.resolve())
