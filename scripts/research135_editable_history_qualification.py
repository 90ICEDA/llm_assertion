"""Development-only inventory and native discrimination qualification; no model.

Explicit bounded population: existing nine FIFO archive entries plus every
unique Ibex model_call candidate in research87..123 real runs and the canonical
shared Ibex baseline. This is NOT a repository-wide or random population claim.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys
import time
import research116_prospective_deepseek as s
from research88_cross_parent_audit import inspect_version

x=s.x
ROOT,read,dump,digest=x.ROOT,x.read,x.dump,x.sha
P=ROOT/'deliverables/research116_prepare_20261025_r01'
FIELDS=('antecedent','consequent','timing','obligations')


def guard():
    opened=set()
    def hook(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        path=str(args[0]).replace('\\','/')
        mode=args[1]
        if isinstance(mode,str) and any(k in mode for k in 'wax+'):return
        if '/deliverables/' not in path:return
        if any(k in path for k in ('/independent','/frozen/','research133_','research134_',
                                   '/excluded_words.json','/protected_records.json','/protected93.json')):
            raise RuntimeError('forbidden_independent_input:'+path)
        opened.add(path)
    sys.addaudithook(hook)
    return opened


def rel(p):return p.relative_to(ROOT).as_posix()


def adapt(value,current=None):
    # Reuse original syntax-only full-set renderer, not the immutable-BRANCH
    # adapter. Labels retain the existing phase checker's a0/OP convention.
    if not isinstance(value,dict) or value.get('operation')!='replace':raise ValueError('full_set_replace_required')
    candidate=x.old.assemble(value,current)
    if len(candidate['assertions'])<2:raise ValueError('branch_and_op_slots_required')
    if candidate['assertions'][0]['obligations']!=['illegal_branch_persists']:raise ValueError('first_slot_branch_label')
    if any(a['obligations']!=['op_bit28_illegal'] for a in candidate['assertions'][1:]):raise ValueError('op_slot_labels')
    for raw,compiled in zip(value['assertions'],candidate['assertions']):
        assert all(raw[k]==compiled[k] for k in FIELDS)
    return candidate


def as_edit(c):return dict(operation='replace',reason='local syntax fixture, never model success',
    assertions=[{k:a[k] for k in FIELDS} for a in c['assertions']])


def inventory(out):
    opened=guard();out.mkdir(parents=True,exist_ok=False)
    dump(out/'population_lock.json',dict(time=time.time(),
        scope='Canonical Ibex shared baseline; ALL unique model_call/candidate.json in research87..123 directories with real in their name; all9 FIFO entries from existing research117 inventory.',
        restrictions='Ibex full151 runtime selected for original historical provenance and existing DeepSeek expression frontend. FIFO entries listed but deferred as different parent/adapter. No model/holdout performance used.',
        order='Canonical preexisting shared baseline first, then lexicographic source path. First qualifying Ibex candidate only; no selection by measured O/H gain.',
        qualification='Healthy complete existing151 development replay; zero baseline false alarms/critical unknown; at least one historical detection AND an unresolved public miss; both obligation components editable. A complete candidate without a public repair target is ineligible for this repair pilot.',
        no_independent_reads=True,no_model_calls=True))
    paths=[P/'initial.json'];discovered=[]
    for root in sorted((ROOT/'deliverables').iterdir()):
        m=re.match(r'research(\d+)_',root.name)
        if not root.is_dir() or not m or not 87<=int(m[1])<=123 or 'real' not in root.name:continue
        for folder,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in ('frozen','independent','source_snapshot','before','after','native','baseline_native')
                     and not d.startswith(('compiled','obj_dir','case_','independent'))]
            if Path(folder).name=='model_call' and 'candidate.json' in files:discovered.append(Path(folder)/'candidate.json')
    paths+=sorted(discovered)
    unique={}
    for path in paths:
        c=read(path);key=x.signature(c)
        row=unique.setdefault(key,dict(id=f'i{len(unique):02d}',parent='ibex166',path=rel(path),
            executable_hash=key,candidate_sha256=digest(path),sources=[],measurements=[]))
        row['sources'].append(dict(path=rel(path),sha256=digest(path)))
        native=P/'baseline_native' if path==P/'initial.json' else path.parent.parent/'native'
        if all((native/cohort/'result.json').exists() for cohort in ('alignment','search','history')) and (native/'decision.json').exists():
            row['measurements'].append(rel(native))
    fifo=read(ROOT/'deliverables/research117_search_prepare_20261025_r01/inventory.json')
    rows=list(unique.values())+[dict(id='fifo_'+c['name'],parent='fifo_artificial_faults',path=c['path'],
        executable_hash=c['executable_hash'],candidate_sha256=c['candidate_sha256'],sources=c['sources'],
        measurements=[],pre_exclusion='Different parent/full105 frontend; retained in population but outside this original-Ibex pilot.') for c in fifo]
    dump(out/'inventory.json',rows)
    bindings={r['path']:digest(ROOT/r['path']) for r in rows}
    for row in unique.values():
        for src in row['sources']:bindings[src['path']]=src['sha256']
    bindings[rel(Path(__file__))]=digest(Path(__file__))
    dump(out/'bindings.json',bindings);dump(out/'read_audit.json',sorted(opened))
    dump(out/'sealed.json',{p.name:digest(p) for p in out.glob('*.json')})
    print('INVENTORY135',len(unique),'Ibex +',len(fifo),'FIFO; model0',flush=True)


def qualify(inv,out):
    opened=guard()
    for name,h in read(inv/'sealed.json').items():assert digest(inv/name)==h
    for name,h in read(inv/'bindings.json').items():assert digest(ROOT/name)==h
    out.mkdir(parents=True,exist_ok=False)
    baseline=read(P/'baseline_full.json');rows=read(inv/'inventory.json');matrix=[];raw_count=0
    for row in rows:
        reasons=[];details=[]
        if row['parent']!='ibex166':reasons.append('different_parent_and_native_frontend_for_this_pilot')
        else:
            c=read(ROOT/row['path'])
            try:assert adapt(as_edit(c))==c
            except (AssertionError,ValueError,KeyError,TypeError):reasons.append('full_set_interface_incompatible')
            if not row['measurements']:reasons.append('no_complete_existing_native151_measurement')
            elif not reasons:
                # First complete source by sealed source order, not the one
                # with the most favorable counts or a known rejection.
                folder=ROOT/row['measurements'][0]
                try:
                    n,ev,rec=inspect_version(folder,c,baseline);raw_count+=n
                    full=x.paired.aggregate(rec['history'],rec['search']);info=x.old.acceptance.inspect(full['ledger'])
                    public_misses=sum(rec[k]['counts']['misses'] for k in ('alignment','search'))
                    details=dict(measurement=rel(folder),native_rows=n,existing_detections=len(info['detections']),
                        existing_false_positives=len(info['false_positives']),critical_unknown=len(info['unknown']),
                        public_misses=public_misses,history_counts=rec['history']['counts'],search_counts=rec['search']['counts'])
                    if not all(rec[k]['healthy'] for k in rec):reasons.append('unhealthy_native')
                    if info['false_positives']:reasons.append('baseline_legal_false_alarms')
                    if info['unknown'] or info['errors']:reasons.append('baseline_unknown_or_integrity_failure')
                    if not info['detections']:reasons.append('no_existing_historical_detection_to_preserve')
                    if not public_misses:reasons.append('no_unresolved_public_repair_target')
                except (AssertionError,KeyError,ValueError,TypeError) as exc:
                    reasons.append('existing_measurement_audit_failed:'+type(exc).__name__)
        matrix.append(dict(**row,eligible=not reasons,exclusion_reasons=reasons,development=details,
            immutable_components=[],eligibility_is_not_model_success=True))
        dump(out/'candidate_matrix.json',matrix)
        print('QUAL135',row['id'],not reasons,reasons,flush=True)
    eligible=[m for m in matrix if m['eligible']]
    if not eligible:
        dump(out/'outcome.json',dict(qualified=False,reason='no_eligible_candidate',model_calls=0));return
    selected=eligible[0];candidate=read(ROOT/selected['path'])
    dump(out/'selection.json',dict(selected=selected['id'],source=selected['path'],eligible_ids=[m['id'] for m in eligible],
        rule='First qualified in locked canonical-baseline/source order; never select by extra-rejection fixture outcome.',
        selected_at=time.time(),candidate_sha256=x.old.acceptance.sha(candidate)))
    dump(out/'initial.json',candidate)
    # This remains an interface/capability qualification. Handwritten controls
    # are private, never a shared real model proposal or request example.
    positive=read(P/'controls/positive/candidate.json')
    source_records={k:read(P/'baseline_native'/k/'result.json') for k in ('alignment','search')}
    words=sorted({row['sample']['instruction'] for rec in source_records.values() for row in rec['ledger']
        if row['obligation']=='illegal_branch_persists'})
    negative=copy.deepcopy(positive)
    a=negative['assertions'][0]
    a['antecedent']='('+a['antecedent']+') && ('+' || '.join(f"instr == 32'h{w:08x}" for w in words)+')'
    negative=adapt(as_edit(negative))
    checks=[];measurements={}
    for name,c in [('baseline',candidate),('local_positive',positive),('local_history_loss',negative)]:
        folder=out/'native_controls'/name;dump(folder/'candidate.json',c)
        ev,rec=x.evaluate(c,folder/'native',baseline)
        n,again,_=inspect_version(folder/'native',c,baseline);raw_count+=n
        assert ev==again
        decisions=dict(O=bool(ev['ordinary']['accepted']),H=bool(ev['full_absolute']))
        measurements[name]=dict(decisions=decisions,lost_detections=len(ev['lost_detection_ids']),
            new_false_alarms=len(ev['new_false_alarm_ids']),retained_detections=len(ev['retained_detection_ids']),
            counts=ev['counts'],local_fixture=name!='baseline',not_model_response=True)
        print('NATIVE135',name,measurements[name],flush=True)
    qualified=(measurements['local_positive']['decisions']==dict(O=True,H=True) and
        measurements['local_history_loss']['decisions']==dict(O=True,H=False) and
        measurements['local_history_loss']['lost_detections']>0)
    # Syntax admission must permit a branch predicate edit, not repair it.
    check_edit=as_edit(candidate);check_edit['assertions'][0]['antecedent']='1\'b0'
    assert adapt(check_edit)['assertions'][0]['antecedent']=="1'b0"
    checks.append('branch_can_be_changed_without_local_semantic_repair')
    for name,change in [('unknown_field',lambda v:v.update(extra=1)),
        ('unknown_signal',lambda v:v['assertions'][0].update(antecedent='secret_signal')),
        ('bad_timing',lambda v:v['assertions'][0].update(timing='later'))]:
        v=as_edit(candidate);change(v)
        try:adapt(v)
        except (AssertionError,ValueError,KeyError):checks.append(name+'_rejected')
        else:raise AssertionError(name)
    dump(out/'fixture_results.private.json',measurements)
    dump(out/'baseline_full.json',baseline)
    dump(out/'checks.json',checks)
    dump(out/'outcome.json',dict(qualified=qualified,model_calls=0,new_accepted_versions=0,new_independent_tests=0,
        native_development_rows_reaudited=raw_count,source_inventory_candidates=len(rows),eligible_candidates=len(eligible),
        selected=selected['id'],native_qualification_compiles=18,native_qualification_experiments=18,
        inference='Local fixture establishes expressible historical loss and O/H discrimination; no prediction that a fresh model proposal will discriminate.',
        H_R_unique_effect=False))
    dump(out/'preparation_cost.json',x.costs.native_cost(out))
    dump(out/'read_audit.json',sorted(opened))
    paths=[inv/'sealed.json',Path(__file__),P/'initial.json',P/'baseline_full.json',P/'request.preview.json']
    paths+=list((ROOT/'scripts').glob('*.py'))
    dump(out/'source_bindings.json',{rel(p):digest(p) for p in paths})
    dump(out/'sealed.json',{rel(p.relative_to(out)) if False else p.relative_to(out).as_posix():digest(p)
        for p in out.rglob('*.json') if 'obj_dir' not in p.parts and p.name!='sealed.json'})
    print('QUALIFIED135',qualified,'model0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('inventory','qualify'))
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--inventory',type=Path)
    a=ap.parse_args()
    if a.action=='inventory':inventory(a.out.resolve())
    else:qualify(a.inventory.resolve(),a.out.resolve())
