"""Registered fresh-input acceptance, callable only after all 24 versions freeze.

Does not read research194 held-out data. Tests reuse the development fault
instances, so results concern input generalization, not unseen-fault detection.
"""
import argparse
import copy
from pathlib import Path
import random
from research195_refinement_prepare import verify
from research195_refinement_fixtures import fixtures,FixtureAdapter,evaluate_locked
import research194_refinement_runner as common
from research194_active_search import combine_candidates,project_measurement
from research194_metrics import temporal_detection

SEEDS=(19583,19597)


def generate(case_id,seed):
    rng=random.Random(seed);rows=[]
    if case_id=='counter':
        def add(**kw):
            row=dict(rst_n=1,clr=0,en=0,load=0,down=0,d=0);row.update(kw);rows.append(row)
        for _ in range(3):add(rst_n=0)
        for _ in range(2):add()
        for _ in range(7):
            add(load=1,d=rng.randrange(1,16))
            for _ in range(rng.randrange(1,4)):add(d=rng.randrange(16))
            for _ in range(rng.randrange(1,5)):add(en=1)
            add();add(clr=1,en=1);add();add()
    elif case_id=='ibex_flush':
        import research194_ibex as ibex
        def add(n=1,**kw):
            for _ in range(n):
                row=dict(rst_n=1,valid=0,ready=0,flush=0,instr=0x13);row.update(kw);rows.append(row)
        first=ibex.instruction('push',rng.choice([6,8,10]),rng.randrange(3))
        second=ibex.instruction('pop',rng.choice([5,8,10]),rng.randrange(3))
        add(3,rst_n=0);add(valid=1,ready=1,instr=first)
        add(rng.randrange(2,5),valid=1,ready=0,instr=first)
        add(valid=1,ready=0,flush=1,instr=first);add(2)
        add(len(ibex.micro_ops(second)),valid=1,ready=1,instr=second);add(3)
    else:raise ValueError('unregistered_case')
    return dict(id=f'{case_id}/r195_fresh/{seed}/'+common.r.digest(rows)[:12],family='r195_fresh',rows=rows,
        obligations=common.cases.get_case(case_id)['obligations'],dimensions=['window','transaction','exception'],
        split='independent',estimated_cost=2,evidence_visibility='heldout_after_all_R195_versions_freeze',
        constraints=['registered input generator','no archived held-out input read'])


def run(prepared,execution,out):
    protocol,seal=verify(prepared);execution=Path(execution);out=Path(out)
    terminal=common.read(execution/'outcome.json')
    if terminal.get('status')!='completed_all_versions_frozen' or terminal.get('population')!=24 or terminal.get('protocol_sha256')!=seal:
        raise ValueError('all_24_registered_versions_must_freeze_before_input_generation')
    entries=[];bindings={}
    for entry in protocol['entries']:
        folder=execution/entry['id']/'refinement';outcome=common.read(folder/'outcome.json');candidate=common.read(folder/'frozen.json')
        if outcome.get('registered_id')!=entry['id'] or outcome.get('status')!='frozen' or common.r.digest(candidate)!=outcome.get('frozen_sha256'):
            raise ValueError('frozen_identity_or_candidate_mismatch')
        FixtureAdapter(entry['fixture']).validate(candidate)
        bindings[str(folder/'frozen.json')]=common.file_hash(folder/'frozen.json')
        entries.append(dict(entry,candidate=candidate,folder=str(folder),candidate_sha256=common.r.digest(candidate)))
    if out.exists():raise ValueError('immutable_independent_destination_exists')
    out.mkdir(parents=True)
    plan={name:[generate(f['case_id'],seed) for seed in SEEDS] for name,f in fixtures().items()}
    development={common.r.digest(q['rows']) for f in fixtures().values() for q in f['queries']}
    if any(common.r.digest(q['rows']) in development for qs in plan.values() for q in qs):raise ValueError('input_overlap_with_development')
    common.dump(out/'plan.json',dict(protocol_sha256=seal,seeds=SEEDS,queries=plan,frozen_bindings=bindings,
        independence='New generated inputs on the same development fault instances; not unseen-fault generalization.'))
    records=[];cost=[]
    for name,fixture in fixtures().items():
        adapter=FixtureAdapter(name);selected=[e for e in entries if e['fixture']==name]
        selected.append(dict(id=name+'/initial_control',fixture=name,role='initial_control',candidate=fixture['initial'],candidate_sha256=common.r.digest(fixture['initial'])))
        versions={e['candidate_sha256']:e['candidate'] for e in selected};keys=list(versions)
        combined,mapping=combine_candidates(list(versions.values()))
        measured=evaluate_locked(fixture['case_id'],combined,out/name/'native',plan[name],fixture['fault'],split='independent',trusted=True)
        cost.append(dict(fixture=name,**measured['cost']))
        common.dump(out/name/'version_mapping.json',dict(keys=keys,mapping=mapping))
        for index,key in enumerate(keys):
            projected=project_measurement(measured,versions[key],mapping,index);projected.update(temporal_detection(projected))
            common.dump(out/name/f'projection{index}.json',projected)
            for entry in selected:
                if entry['candidate_sha256']!=key:continue
                records.append(dict(id=entry['id'],fixture=name,case_id=fixture['case_id'],seed=entry.get('seed'),arm=entry.get('arm'),
                    role=entry.get('role','model_trajectory'),candidate_sha256=key,targets=projected['targets'],
                    timely_detected_ids=projected['detected_ids'],transaction_detected_ids=projected['transaction_detected_ids'],
                    false_positives=projected['false_positives'],critical_unknown=projected['critical_unknown'],
                    native_complete=projected['native_complete'],reference_complete=projected['reference_complete'],
                    projection=str(out/name/f'projection{index}.json')))
        common.dump(out/'results.json',records);common.dump(out/'physical_cost.json',cost)
    if any(common.file_hash(path)!=value for path,value in bindings.items()):raise ValueError('frozen_candidate_changed')
    common.dump(out/'outcome.json',dict(status='completed',frozen_population=24,initial_controls=4,
        source_protocol_sha256=seal,model_calls=0,native_compile_attempts=sum(c['native_compile_attempts'] for c in cost),
        native_execution_attempts=sum(c['native_execution_attempts'] for c in cost),frozen_unchanged=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--execution',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();run(args.prepared,args.execution,args.out)
