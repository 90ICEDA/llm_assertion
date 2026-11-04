"""Native cross-design, held-out-fault validation after every model version freezes.

Physical jobs may share immutable assertion properties. Every version is judged
only by its own labels, and all unseen faults are qualified before receiving
detection credit. Synthetic cohorts and original upstream bugs stay separate.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

import research194_cases as cases
import research194_ibex as ibex
from research194_active_search import combine_candidates,project_measurement
from research194_metrics import temporal_detection

ROOT=Path(__file__).resolve().parents[1]
REGISTRATION=ROOT/'deliverables/reguard_mechanisms_20261103_r02/acceptance_registration.json'
SOURCE_NAMES=('research194_independent.py','research194_cases.py','research194_ibex.py',
              'research194_active_search.py','research194_active_semantics.py','research194_metrics.py','research_native_runner.py')


def population():
    arms=(('S0','R0'),('S0','R1'),('S0','R2'),('S0','R3'),('S1','R1'),('S2','R1'),('S3','R1'),('S3','R3'))
    rows=[]
    for case_id in ('arbiter','counter','uart','ibex_flush'):
        for seed in (19407,19419):
            for search,strategy in arms:
                rows.append(dict(id=f'base/{case_id}/{seed}/{search}_{strategy}',case_id=case_id,seed=seed,search_strategy=search,strategy=strategy))
            for condition in ('without','with'):
                rows.append(dict(id=f'augmentation/{case_id}/{seed}/{condition}',case_id=case_id,seed=seed,
                    search_strategy='augmentation_'+condition,strategy='R3',condition=condition))
    return rows


def register(out=REGISTRATION):
    if out.exists():raise ValueError('registration_already_exists')
    bindings={str(ROOT/'scripts'/n):sha(ROOT/'scripts'/n) for n in SOURCE_NAMES}
    for case_id in ('arbiter','counter','uart','ibex_flush'):
        for source in cases.get_case(case_id)['sources']:
            path=ROOT/source;bindings[str(path)]=sha(path)
    for directory in ('external/common_cells/include','external/opentitan/hw/ip/prim/rtl'):
        for path in (ROOT/directory).rglob('*.svh'):bindings[str(path)]=sha(path)
    cases.dump(out,dict(entries=population(),source_bindings=bindings,
        scope='80 fixed trajectories plus four frozen initial controls. No independent inputs constructed or executed at registration.'))


def collect(main,augmentation,out):
    entries=[]
    for row in population():
        parts=row['id'].split('/')
        folder=(Path(main) if parts[0]=='base' else Path(augmentation))/Path(*parts[1:])/'refinement'
        entries.append(dict(**row,folder=str(folder.resolve().relative_to(ROOT))))
    cases.dump(out,entries)


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(entries,expected,out):
    if len(entries)!=expected:raise ValueError('incomplete_campaign_population')
    registered=read(REGISTRATION)
    registry={e['id']:e for e in registered['entries']}
    if expected!=len(registry) or {e['id'] for e in entries}!=set(registry):raise ValueError('registered_population_mismatch')
    for path,value in registered['source_bindings'].items():
        if sha(path)!=value:raise ValueError('preregistered_source_changed')
    records=[];ids=set();folders=set()
    for entry in entries:
        identity=entry['id']
        if identity in ids:raise ValueError('duplicate_trajectory')
        ids.add(identity)
        folder=(ROOT/entry['folder']).resolve();terminal=read(folder/'outcome.json')
        if folder in folders:raise ValueError('duplicate_trajectory_folder')
        folders.add(folder)
        for field,value in registry[identity].items():
            if entry.get(field)!=value:raise ValueError('entry_identity_mismatch:'+field)
            if field!='id' and terminal.get(field)!=value:raise ValueError('terminal_identity_mismatch:'+field)
        if terminal.get('status')!='frozen':raise ValueError('trajectory_not_closed')
        if terminal.get('provenance')!='real_remote_model':raise ValueError('non_model_trajectory_in_model_comparison')
        path=folder/'frozen.json';candidate=read(path)
        if cases.digest(candidate)!=terminal['frozen_sha256']:raise ValueError('candidate_binding')
        cases.validate(entry['case_id'],candidate)
        records.append(dict(**entry,path=path.relative_to(ROOT).as_posix(),sha256=sha(path),
            outcome_path=(folder/'outcome.json').relative_to(ROOT).as_posix(),outcome_sha256=sha(folder/'outcome.json'),
            candidate_sha256=cases.digest(candidate)))
    out=Path(out)
    if out.exists():raise ValueError('immutable_freeze_exists')
    controls=[]
    for case_id in sorted({e['case_id'] for e in entries}):
        candidate=cases.get_case(case_id)['initial']
        controls.append(dict(id=case_id+'/initial_control',case_id=case_id,role='initial_control',
            candidate=candidate,candidate_sha256=cases.digest(candidate)))
    cases.dump(out,dict(all_trajectories_closed=True,expected=expected,entries=records,controls=controls,
        registration_sha256=sha(REGISTRATION),source_bindings=registered['source_bindings'],
        rule='No independent inputs or fault runs until all registered base and augmentation trajectories close.'))


def execute(manifest,out):
    manifest=Path(manifest).resolve();out=Path(out).resolve()
    data=read(manifest)
    if not data.get('all_trajectories_closed') or len(data['entries'])!=data['expected']:raise ValueError('incomplete_freeze')
    if sha(REGISTRATION)!=data['registration_sha256']:raise ValueError('registration_changed')
    for path,value in data['source_bindings'].items():
        if sha(path)!=value:raise ValueError('registered_test_definition_changed')
    entries=data['entries'];out.mkdir(parents=True,exist_ok=False)
    ibex.register()
    bindings={str(manifest):sha(manifest)}
    for name in SOURCE_NAMES:
        path=ROOT/'scripts'/name;bindings[str(path)]=sha(path)
    for case_id in sorted({e['case_id'] for e in entries}):
        for name in cases.get_case(case_id)['sources']:
            path=ROOT/name;bindings[str(path)]=sha(path)
    for directory in ('external/common_cells/include','external/opentitan/hw/ip/prim/rtl'):
        for path in (ROOT/directory).rglob('*.svh'):bindings[str(path)]=sha(path)
    for e in entries:
        for field,key in (('path','sha256'),('outcome_path','outcome_sha256')):
            path=ROOT/e[field]
            if sha(path)!=e[key]:raise ValueError('frozen_artifact_changed')
            bindings[str(path)]=e[key]
        if cases.digest(read(ROOT/e['path']))!=e['candidate_sha256']:raise ValueError('candidate_changed')
    for control in data['controls']:
        if cases.digest(control['candidate'])!=control['candidate_sha256']:raise ValueError('initial_control_changed')
        cases.validate(control['case_id'],control['candidate'])
    entries=entries+data['controls']
    # Fixed test construction occurs only after the complete immutable freeze.
    plans={}
    for case_id in sorted({e['case_id'] for e in entries}):
        query_sets=[cases.query_pool(case_id,'independent',s) for s in (19407,19419)]
        queries={cases.digest(q['rows']):q for group in query_sets for q in group}
        development={cases.digest(q['rows']) for s in (19407,19419) for q in cases.query_pool(case_id,'development',s)}
        if development & set(queries):raise ValueError('independent_input_overlap')
        faults=[f for f in cases.FAULTS[case_id] if f['split']=='independent']
        dev=[f for f in cases.FAULTS[case_id] if f['split']=='development']
        if {f['site'] for f in faults}&{f['site'] for f in dev}:raise ValueError('independent_site_overlap')
        operator_overlap={f['operator'] for f in faults}&{f['operator'] for f in dev}
        plans[case_id]=dict(queries=list(queries.values()),faults=['primary']+[f['id'] for f in faults],
            split_audit=dict(development_sites=[f['site'] for f in dev],test_sites=[f['site'] for f in faults],
                development_operators=[f['operator'] for f in dev],test_operators=[f['operator'] for f in faults],
                exact_operator_overlap=sorted(operator_overlap),
                scope='Different exact sites are required. Distinct operator names do not establish disjoint broad operator families.'))
    cases.dump(out/'plan.json',plans)
    cases.dump(out/'plan_seal.json',dict(manifest_sha256=sha(manifest),plan_sha256=sha(out/'plan.json'),selected_after_all_frozen=True))
    cases.dump(out/'bindings.json',bindings)
    records=[];physical=[];started=time.monotonic()
    for case_id,plan in plans.items():
        versions={};groups={}
        for e in entries:
            if e['case_id']!=case_id:continue
            candidate=cases.validate(case_id,e['candidate'] if e.get('role')=='initial_control' else read(ROOT/e['path']));key=cases.digest(candidate)
            versions.setdefault(key,candidate);groups.setdefault(key,[]).append(e)
        keys=list(versions);combined,mapping=combine_candidates([versions[k] for k in keys])
        cases.dump(out/case_id/'version_mapping.json',dict(keys=keys,mapping=mapping,combined=combined))
        for fault in plan['faults']:
            m=cases.evaluate(case_id,combined,out/case_id/fault,queries=plan['queries'],split='independent',fault=fault,_trusted_bundle=True)
            physical.append(dict(case_id=case_id,fault=fault,**m['cost']))
            oracle_unknown=[u for u in m['critical_unknown'] if not u.get('assertion')]
            fault_valid=bool(m['targets']) and m['native_complete'] and not oracle_unknown
            cases.dump(out/case_id/fault/'fault_qualification.json',dict(
                valid_reachable_fault=fault_valid,oracle_unknown=oracle_unknown,
                confirmed_target_count=len(m['targets']),
                rule='Qualification uses native completion and independent reference only, never candidate alarms or candidate-specific unknown.'))
            for index,key in enumerate(keys):
                projected=project_measurement(m,versions[key],mapping,index)
                temporal=temporal_detection(projected);projected.update(temporal)
                exposed=set(projected['targets']);detected=set(projected['detected_ids'])
                any_detected=set(temporal['transaction_detected_ids'])
                unknown=projected['critical_unknown'];fp=projected['false_positives']
                observations=projected['evidence']
                qids={q['id'] for q in plan['queries']}
                unknown_queries={u.get('query') for u in projected['critical_unknown'] if u.get('query')}
                for job in projected['executions']:
                    if job['result'].get('compile_status')!='passed' or job['result'].get('execution_status')!='completed' or job['reference']['unknown']:
                        unknown_queries.add(job['query_id'])
                exposed_queries={e['query_id'] for e in observations if e['status']=='confirmed' and e['label']=='violation'}
                covered=set(projected['covered_obligations'])
                target_obligations={e['obligation'] for e in observations if e['status']=='confirmed' and e['label']=='violation' and e.get('counted_target')}
                protected={ob for ob in target_obligations if not {e['id'] for e in observations if e['status']=='confirmed' and e['obligation']==ob and e.get('counted_target')}-detected}
                any_protected={ob for ob in target_obligations if not {e['id'] for e in observations if e['status']=='confirmed' and e['obligation']==ob and e.get('counted_target')}-any_detected}
                necessary=set(cases.get_case(case_id)['obligations'])
                metric=dict(parent_bug=projected['parent_bug'],historical_fix_confirmed=projected['historical_fix_confirmed'],
                    fault=fault,fault_kind='original_or_development_primary' if fault=='primary' else 'unseen_fault_at_reserved_site',
                    native_complete=projected['native_complete'],reference_complete=projected['reference_complete'],
                    valid_reachable_fault=fault_valid,
                    target_transaction_obligations=len(exposed),target_transactions=len(projected['target_transaction_ids']),
                    target_ids=sorted(exposed),detected_ids=sorted(detected),missed_ids=sorted(exposed-detected),
                    detected=len(detected),misses=len(exposed-detected),false_positive_records=len(fp),unknown_records=len(unknown),
                    transaction_detected=len(any_detected),late_detected=len(any_detected-detected),transaction_misses=len(exposed-any_detected),
                    transaction_detected_ids=sorted(any_detected),transaction_missed_ids=sorted(exposed-any_detected),
                    detection_delay_cycles=temporal['detection_delay_cycles'],
                    untriggered=len(exposed-set(projected['triggered_ids'])),
                    exposed_obligations=sorted(target_obligations),fully_protected_exposed_obligations=sorted(protected),
                    necessary_obligations=sorted(necessary),unexposed_obligations=sorted(necessary-target_obligations),
                    fully_transaction_protected_exposed_obligations=sorted(any_protected),
                    necessary_obligation_timely_protection_rate=len(protected)/len(necessary),
                    necessary_obligation_transaction_protection_rate=len(any_protected)/len(necessary),
                    unknown_queries=sorted(unknown_queries),no_exposure_queries=sorted(qids-exposed_queries-unknown_queries),
                    full_planned_scope_pass=bool(exposed) and not(exposed-detected) and not fp and not unknown and qids==exposed_queries,
                    full_planned_transaction_scope_pass=bool(exposed) and not(exposed-any_detected) and not fp and not unknown and qids==exposed_queries,
                    all_necessary_obligations_protected=necessary<=any_protected and not fp and not unknown,
                    qualifying_fault_detected=bool(detected) and not unknown and projected['native_complete'] and projected['reference_complete'])
                cases.dump(out/case_id/fault/f'projection{index}.json',projected)
                records.extend({**e,**metric} for e in groups[key])
            cases.dump(out/'results.json',records);cases.dump(out/'physical_cost.json',physical)
            print('INDEPENDENT',case_id,fault,'versions',len(keys),flush=True)
    for name,value in bindings.items():
        if sha(name)!=value:raise ValueError('bound_source_changed_during_acceptance')
    cases.dump(out/'outcome.json',dict(status='completed',frozen_versions=data['expected'],initial_controls=len(data['controls']),all_frozen_unchanged=True,
        model_calls=0,physical_compiles=sum(x['native_compile_attempts'] for x in physical),
        physical_executions=sum(x['native_execution_attempts'] for x in physical),wall_seconds=time.monotonic()-started,
        interpretation='Execution completion is separate from per-version scope acceptance. Unexposed or unknown faults are not passed or misses.'))


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('register')
    c=sub.add_parser('collect');c.add_argument('--main',type=Path,required=True);c.add_argument('--augmentation',type=Path,required=True);c.add_argument('--out',type=Path,required=True)
    f=sub.add_parser('freeze');f.add_argument('--entries',type=Path,required=True);f.add_argument('--expected',type=int,required=True);f.add_argument('--out',type=Path,required=True)
    v=sub.add_parser('run');v.add_argument('--manifest',type=Path,required=True);v.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.action=='register':register()
    elif args.action=='collect':collect(args.main,args.augmentation,args.out)
    elif args.action=='freeze':freeze(read(args.entries),args.expected,args.out)
    else:execute(args.manifest,args.out)
