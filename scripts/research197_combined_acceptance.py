"""One post-freeze native acceptance for 66 original plus 6 corrected versions.

Fault definitions, seeds and generators are the original sealed R197 ones.
The original-results view filters membership only, preserving physical hashes.
"""
import argparse
import copy
from pathlib import Path
import shutil
from research194_refinement_runner import ROOT,read,dump,file_hash
from research197_independent import runtime


def register(prepared,corrected,main_execution,corrected_execution,out):
    prepared,corrected,main_execution,corrected_execution,out=map(Path,(prepared,corrected,main_execution,corrected_execution,out))
    p=read(prepared/'protocol.json');q=read(corrected/'protocol.json');original=read(prepared/'acceptance_registration.json')
    if q['original_protocol_sha256']!=file_hash(prepared/'protocol.json'):raise ValueError('original_binding')
    entries=copy.deepcopy(original['entries'])
    for e in q['entries']:entries.append(dict(id=e['id']+'_corrected',case_id=e['case_id'],seed=e['seed'],search_strategy='S0',strategy='R3'))
    if len(entries)!=72 or len({e['id'] for e in entries})!=72:raise ValueError('population')
    bindings={**p['source_bindings'],**q['source_bindings']}
    for path in (Path(__file__),ROOT/'scripts/research197_typed_execute.py',prepared/'protocol.json',corrected/'protocol.json'):
        bindings[str(path.resolve())]=file_hash(path)
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'registration.json',dict(entries=entries,source_bindings=bindings,faults=original['faults'],independent_seeds=original['independent_seeds'],
        inputs_constructed=False,main_execution=str(main_execution.resolve()),corrected_execution=str(corrected_execution.resolve()),
        scope='Original sealed acceptance definitions, augmented frozen population only. Original and corrected T stay separate.'))
    dump(out/'seal.json',dict(sha256=file_hash(out/'registration.json')))
    print(dict(registered_versions=72,independent_inputs_constructed=False),flush=True)


def run(registration,out):
    registration,out=Path(registration),Path(out);reg=read(registration/'registration.json')
    if file_hash(registration/'registration.json')!=read(registration/'seal.json')['sha256']:raise ValueError('registration_changed')
    for name in ('main_execution','corrected_execution'):
        if read(Path(reg[name])/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('all_72_versions_must_freeze')
    entries=[]
    for e in reg['entries']:
        corrected=e['id'].endswith('_corrected');identity=e['id'].removesuffix('_corrected') if corrected else e['id']
        base=Path(reg['corrected_execution'] if corrected else reg['main_execution'])
        entries.append(dict(e,folder=str((base/identity/'refinement').resolve().relative_to(ROOT))))
    if out.exists():raise ValueError('immutable_acceptance')
    module=runtime(registration/'registration.json');module.freeze(entries,72,out/'freeze.json');module.execute(out/'freeze.json',out/'native')


def original_view(combined,prepared,out):
    combined,prepared,out=map(Path,(combined,prepared,out));source=combined/'native'
    if read(source/'outcome.json')['status']!='completed':raise ValueError('acceptance_incomplete')
    out.mkdir(parents=True,exist_ok=False);native=out/'native';native.mkdir()
    p=read(prepared/'protocol.json');ids={e['id'] for e in p['entries']};controls={cid+'/initial_control' for cid in p['case_ids']}
    results=[r for r in read(source/'results.json') if r['id'] in ids|controls]
    freeze=read(combined/'freeze.json');freeze['entries']=[e for e in freeze['entries'] if e['id'] in ids];freeze['expected']=len(ids)
    freeze['derived_view_only']=True;freeze['authoritative_manifest']=str((combined/'freeze.json').resolve());freeze['authoritative_manifest_sha256']=file_hash(combined/'freeze.json')
    dump(out/'freeze.json',freeze)
    copied=[]
    for path in source.rglob('*.json'):
        relative=path.relative_to(source)
        if path.name not in ('plan.json','plan_seal.json','bindings.json','physical_cost.json','version_mapping.json') and not path.name.startswith('projection'):continue
        dest=native/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
        copied.append(dict(source=str(path.resolve()),destination=str(dest.resolve()),sha256=file_hash(path)))
    dump(native/'results.json',results);outcome=read(source/'outcome.json');outcome.update(frozen_versions=66,derived_membership_view=True,
        shared_physical_bundle=str(source.resolve()),physical_cost_must_not_be_added_again=True)
    dump(native/'outcome.json',outcome);dump(native/'view_provenance.json',dict(copied=copied,results_source_sha256=file_hash(source/'results.json'),
        transformation='Only membership filtering; measurements, plans, projection indices and actual physical costs are shared unchanged.'))
    print(dict(original_versions=len(ids),version_fault_records=len(results)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','run','view'])
    for key in ('prepared','corrected','main-execution','corrected-execution','registration','combined'):p.add_argument('--'+key,type=Path)
    p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    if a.action=='register':register(a.prepared,a.corrected,a.main_execution,a.corrected_execution,a.out)
    elif a.action=='run':run(a.registration,a.out)
    else:original_view(a.combined,a.prepared,a.out)
