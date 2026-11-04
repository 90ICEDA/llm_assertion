"""Seal exact paired single-round requests; no model transport or credentials."""
import argparse
import ast
from pathlib import Path
from research195_refinement_adapter import runtime
from research195_refinement_fixtures import fixtures,FixtureAdapter
import research194_refinement_runner as common

ROOT=Path(__file__).resolve().parents[1]
SEEDS=(19507,19519)


def source_bindings():
    bindings=common.source_bindings()
    pending=[Path(__file__),Path(__file__).with_name('research195_refinement_execute.py'),Path(__file__).with_name('research195_refinement_independent.py')]
    while pending:
        path=pending.pop()
        if str(path) in bindings:continue
        bindings[str(path)]=common.file_hash(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
            for name in names:
                if name and name.startswith('research'):
                    dep=ROOT/'scripts'/(name+'.py')
                    if dep.is_file():pending.append(dep)
    for fixture in fixtures().values():
        for source in common.cases.get_case(fixture['case_id'])['sources']:
            path=ROOT/source;bindings[str(path)]=common.file_hash(path)
            for header in path.parent.rglob('*.svh'):bindings[str(header)]=common.file_hash(header)
    for folder in ('external/common_cells/include','external/opentitan/hw/ip/prim/rtl'):
        for path in (ROOT/folder).rglob('*.svh'):bindings[str(path)]=common.file_hash(path)
    return bindings


def prepare(qualification,out):
    qualification=Path(qualification);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if common.read(qualification/'outcome.json')['status']!='completed':raise ValueError('qualification_not_completed')
    entries=[]
    for name,fixture in fixtures().items():
        adapter=FixtureAdapter(name)
        raw=common.read(qualification/name/'before/measurement.json')
        before=common.bind_measurement(raw,fixture['initial'])
        for seed in SEEDS:
            for arm in ('F','P','L'):
                core,runner=runtime(arm);folder=out/name/str(seed)/arm
                acquired=dict(queries=fixture['queries'],measurement=before,task_id=f'R195/{name}/shared-native-evidence',
                    cost=dict(native_compile_attempts=0,native_execution_attempts=0,physical_native_jobs=0,source_measurement=str(qualification/name/'before/measurement.json')))
                prepared=runner.prepare_first(adapter,'R3',seed,before,fixture['queries'],acquired,folder,max_rounds=1)
                blocked=bool(before['critical_unknown'] or not before['native_complete'] or not before['reference_complete'])
                entries.append(dict(id=f'{name}/{seed}/{arm}',fixture=name,case_id=adapter.case_id,seed=seed,arm=arm,
                    mode='blocked_unknown' if blocked else 'ready',**prepared))
    protocol=dict(version='research195',endpoint=common.ENDPOINT,model='deepseek/deepseek-v3-0324',
        temperature=.2,max_output_tokens=2048,timeout_seconds=300,retries=0,workers=2,max_rounds=1,
        seeds=SEEDS,population=24,maximum_model_calls=sum(e['mode']=='ready' for e in entries),
        population_call_ceiling=24,arms=dict(F='free edits without localization hints',P='free edits with localization hints',L='localized field edits with same hints'),
        shared=dict(evidence='exact same native before measurement within each fixture; reused across provider seeds',
            gate='R3 complete observed history, timely and any-cycle protection',output_budget=2048,composition=False,regeneration=False,
            structure='Identical fixed label set and per-label obligation mappings; no adding/deleting/rebinding assertions in any arm.'),
        native_budget=dict(maximum_proposal_native_jobs=sum(2*len(fixtures()[e['fixture']]['queries']) for e in entries if e['mode']=='ready'),
            public_qualification_cost_separate=True,no_unpaid_hidden_gate_queries=True),
        external_payload='Public original RTL/specification, defective SVA and native development evidence; no independent inputs or fault definitions.',
        authorization='NOT AUTHORIZED. Requires a new research195 user authorization bound to this seal. Earlier research194 permission cannot be used.',
        independent_protocol='Freeze all 24 registered versions, including blocked/failed initial versions, before constructing new held-out inputs. Research194 independent inputs are not new holdout.',
        independent_generator=dict(script='scripts/research195_refinement_independent.py',seeds=[19583,19597],
            native_jobs=16,initial_controls=4,scope='New inputs only; development fault instances reused, no unseen-fault generalization claim.'),
        qualification=str(qualification.resolve()),source_bindings=source_bindings(),entries=entries)
    common.dump(out/'protocol.json',protocol)
    common.dump(out/'seal.json',dict(version='research195',protocol_sha256=common.file_hash(out/'protocol.json')))
    sizes=[Path(e['request']).stat().st_size for e in entries]
    review=dict(population=24,exact_requests=len(entries),callable_requests=protocol['maximum_model_calls'],
        blocked_initial=sum(e['mode']=='blocked_unknown' for e in entries),request_bytes=sum(sizes),maximum_request_bytes=max(sizes),
        callable_request_bytes=sum(Path(e['request']).stat().st_size for e in entries if e['mode']=='ready'),
        maximum_callable_request_bytes=max(Path(e['request']).stat().st_size for e in entries if e['mode']=='ready'),
        protocol=str(out/'protocol.json'),seal=str(out/'seal.json'),new_model_calls=0)
    common.dump(out/'review.json',review);print(review)
    pair_audit=[]
    for name in fixtures():
        for seed in SEEDS:
            group=[e for e in entries if e['fixture']==name and e['seed']==seed]
            states=[common.read(e['state']) for e in group]
            evidence_hashes={common.r.digest(s['public_evidence']) for s in states}
            structure_hashes={common.r.digest({a['label']:a['obligations'] for a in s['initial']}) for s in states}
            initial_hashes={common.r.digest(s['initial']) for s in states}
            pair_audit.append(dict(fixture=name,seed=seed,arms=[e['arm'] for e in group],same_evidence=len(evidence_hashes)==1,
                evidence_sha256=sorted(evidence_hashes),same_structure=len(structure_hashes)==1,structure_sha256=sorted(structure_hashes),
                same_initial=len(initial_hashes)==1,initial_sha256=sorted(initial_hashes),same_gate='R3',same_max_output=2048))
    if not all(p['same_evidence'] and p['same_structure'] and p['same_initial'] for p in pair_audit):raise ValueError('paired_information_mismatch')
    common.dump(out/'paired_information_audit.json',pair_audit)


def verify(prepared):
    protocol,seal=common.verify_package(prepared)
    if protocol['version']!='research195' or protocol['population']!=24 or protocol['max_rounds']!=1 or protocol['maximum_model_calls']>24:raise ValueError('R195_protocol_configuration')
    for entry in protocol['entries']:
        core,runner=runtime(entry['arm']);state=common.read(entry['state']);adapter=FixtureAdapter(entry['fixture'])
        ctl=runner.controller_from(adapter,'R3',state['baseline'],1)
        request=core.build_request(adapter.case,ctl,state['public_evidence'],entry['seed'],0)
        if request!=common.read(entry['request']):raise ValueError('exact_request_reconstruction_changed')
    return protocol,seal


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','verify'])
    p.add_argument('--qualification',type=Path);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.command=='prepare':prepare(args.qualification,args.out)
    else:protocol,seal=verify(args.out);print(dict(verified=True,seal=seal,maximum_calls=protocol['maximum_model_calls']))
