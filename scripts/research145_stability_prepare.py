"""Development-only inventory and sealed candidate x seed stability batch.

Uses ALL qualifying unique real Ibex candidates in a bounded source population;
no independent inputs/outcomes or archived complete solutions in model prompts.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import time
from unittest.mock import patch
import research142_mapped_history_pilot as c

ROOT,read,dump,digest,rel=c.ROOT,c.read,c.dump,c.digest,c.rel
SEEDS=(14501,14509,14519)
PURPOSE='research145_candidate_seed_stability'
PREVIOUS=ROOT/'deliverables/research142_prepare_20261027_r01'


def inspect_cached(folder,candidate):
    """Raw native re-audit; recompute label gates without rewriting old results."""
    rows=sum(c.x.g.prior.diagnostic.audit_native(folder/k,candidate,c.x.P,k) for k in ('alignment','search','history'))
    records={k:read(folder/k/'result.json') for k in ('alignment','search','history')}
    for result in records.values():c.mapping.validate_ledger(result,candidate)
    small=records['alignment'];gate=copy.deepcopy(read(folder/'alignment/alignment_gate.json'))
    expected=c.mapping.alignment_base.prior.previous.source_check(c.x.P)['expected']['windows']
    windows=read(c.x.P/'windows.public.json')
    for b in gate['bindings']:
        w=next(w for w in windows if w['id']==b['window'])
        truth=next(w for w in expected if w['id']==b['window'])
        refs=[r for r in small['reference'] if r['transaction_id']==w['transaction_id'] and r['phase']==w['phase'] and r['configuration']==w['configuration']]
        assert len(refs)==1
        ref=refs[0]
        assert ref['instruction']==int(w['instruction_hex'],16) and ref['instr_new']==w['instr_new']
        assert all(ref['actual'][rev]==w[rev+'_illegal'] for rev in ('before','after'))
        bound=[r for r in small['ledger'] if r['sample']['sample_id']==ref['sample_id'] and r['configuration']==w['configuration']]
        triggered=len(bound)==2 and all(any(a['trigger'] for a in c.mapping.mapped_assertions(r,candidate,c.mapping.OP)) for r in bound)
        b.update(replay_sample_id=ref['sample_id'],original_sampling_matches=True,op_required=truth['op_applicable'],
                 op_triggered_on_both_revisions=triggered,accepted=not truth['op_applicable'] or triggered)
    gate['focus12']=c.mapping.focus_gate(small,read(c.x.P/'focus.private.json'),candidate)
    gate['all_property_guard']=c.x.all_guard(folder/'alignment',small,candidate)
    gate['accepted']=bool(c.x.old.admissible(small) and gate['all_property_guard']['accepted'] and gate['focus12']['accepted'] and all(b['accepted'] for b in gate['bindings']))
    full=c.x.paired.aggregate(records['history'],records['search'])
    decision=c.mapping.decide(candidate,full,records,gate,folder)
    return rows,records,full,decision


def inventory():
    paths=[c.p.q.P/'initial.json'];raw_only=[]
    for root in sorted((ROOT/'deliverables').iterdir()):
        match=re.match(r'research(\d+)_',root.name)
        if not root.is_dir() or not match or not 87<=int(match[1])<=144 or 'real' not in root.name:continue
        for folder,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in ('frozen','terminal_frozen','independent','source_snapshot','before','after','native','baseline_native')
                     and not d.startswith(('compiled','obj_dir','case_','independent'))]
            if Path(folder).name!='model_call':continue
            f=Path(folder)
            if 'candidate.json' in files:paths.append(f/'candidate.json')
            elif 'model_edit.json' in files:
                raw_only.append(dict(path=rel(f/'model_edit.json'),sha256=digest(f/'model_edit.json'),
                                     eligible=False,exclusion_reasons=['no_executable_candidate_in_original_run']))
    unique={}
    for path in paths:
        candidate=read(path);signature=c.x.signature(candidate)
        row=unique.setdefault(signature,dict(id=f'c{len(unique):02d}',parent='ibex166_original_decoder',
            path=rel(path),candidate_sha256=digest(path),signature=signature,sources=[],measurements=[]))
        row['sources'].append(dict(path=rel(path),sha256=digest(path)))
        native=c.p.q.P/'baseline_native' if path==paths[0] else path.parent.parent/'native'
        if all((native/k/'result.json').exists() for k in ('alignment','search','history')) and (native/'decision.json').exists():
            row['measurements'].append(rel(native))
    # Same FIFO population retained with an explicit adapter limitation, never
    # silently removed because this experiment uses the original Ibex decoder.
    fifo=[dict(v) for v in read(c.p.QUAL/'candidate_matrix.json') if v['parent']!='ibex166']
    return list(unique.values()),fifo,raw_only


def strata(info):
    groups={}
    for key in sorted(info['misses']):
        row=info['rows'][key];phase=row['sample']['phase']
        label='first' if phase==0 else 'first_held' if phase==1 else 'later_held'
        trigger='triggered_insufficient' if key in info['triggers'] else 'untriggered'
        group=row['obligation']+'/'+label+'/'+trigger
        groups.setdefault(group,[]).append(key)
    return groups


def prepare(out):
    opened=c.p.q.guard();c.verify(PREVIOUS)
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'population_lock.json',dict(at=time.time(),source_range='Canonical partial baseline + ALL unique executable model_call candidates in research87..144 real directories; all9 prior FIFO entries listed separately; raw-only responses listed as ineligible.',
        eligibility='Exact syntax-only new adapter compatibility; complete healthy original current9/search36/history115 native records; zero legal FP and critical unknown including all-property guards; some historical detections AND unresolved public misses.',
        selection='Include ALL qualifying candidates, fixed source ordering. Do not choose by expected benefit or any independent outcome.',
        seeds=list(SEEDS),order='Seed-major then locked candidate order; no replacement after a failure.',
        scope='One original decoder parent, correlated archived candidates; not independent bugs, cross-parent generalization or a search-benefit experiment. New calls only count as replication.',
        no_holdout_reads=True))
    rows,fifo,raw_only=inventory();dump(out/'inventory.json',rows);dump(out/'raw_only_exclusions.json',raw_only)
    matrix=[];qualified=[];read_rows=0;mechanisms={};bindings={}
    for row in rows:
        candidate=read(ROOT/row['path']);reasons=[];details=None
        try:assert c.mapping.adapt(c.p.q.as_edit(candidate))==candidate
        except (AssertionError,ValueError,TypeError,KeyError):reasons.append('new_interface_incompatible')
        if not row['measurements']:reasons.append('no_complete_native_development_replay')
        if not reasons:
            native=ROOT/row['measurements'][0]
            try:
                n,records,full,decision=inspect_cached(native,candidate);read_rows+=n
                info=c.x.old.acceptance.inspect(full['ledger'])
                public_misses=sum(records[k]['counts']['misses'] for k in ('alignment','search'))
                unknown=c.critical_unknown(decision)
                all_fp=sum(len(g['false_alarms']) for g in decision['all_property_guards'].values())+len(decision['current_gate']['all_property_guard']['false_alarms'])
                if not all(r['healthy'] for r in records.values()):reasons.append('native_unhealthy')
                if info['false_positives'] or all_fp:reasons.append('baseline_legal_false_alarms')
                if unknown or info['errors']:reasons.append('baseline_unknown_or_integrity_error')
                if not info['detections']:reasons.append('no_historical_protection')
                if not public_misses:reasons.append('no_public_repair_target')
                groups=strata(info)
                profile=c.x.old.acceptance.sha({k:sorted(info[k]) for k in ('detections','misses','triggers','false_positives','unknown')})
                details=dict(measurement=rel(native),native_rows=n,detections=len(info['detections']),misses=len(info['misses']),
                             public_misses=public_misses,false_positives=len(info['false_positives']),critical_unknown=unknown,
                             behavior_profile=profile,strata={k:len(v) for k,v in groups.items()})
                for k,ids in groups.items():mechanisms.setdefault(k,set()).update(ids)
                if not reasons:
                    q=out/'candidates'/row['id'];q.mkdir(parents=True)
                    dump(q/'initial.json',candidate);dump(q/'baseline_full.json',full)
                    dump(q/'baseline_binding.json',dict(native=rel(native),candidate=rel(ROOT/row['path'])))
                    dump(q/'mechanism_targets.private.json',groups)
                    qualified.append(dict(**row,development=details))
                for f in native.rglob('*'):
                    if f.is_file() and 'obj_dir' not in f.parts:bindings[rel(f)]=digest(f)
            except (AssertionError,ValueError,KeyError,TypeError) as exc:
                reasons.append('raw_reaudit_failed_'+type(exc).__name__)
        matrix.append(dict(**row,eligible=not reasons,exclusion_reasons=reasons,development=details))
        print('QUAL145',row['id'],not reasons,reasons,details and details['strata'],flush=True)
    for row in fifo:
        matrix.append(dict(id=row['id'],parent=row['parent'],path=row['path'],eligible=False,
                           exclusion_reasons=['different_parent_and_native_frontend_outside_this_bounded_batch']))
    dump(out/'candidate_matrix.json',matrix)
    if not qualified:raise RuntimeError('no_qualified_candidates')
    cells=[]
    for seed in SEEDS:
        for row in qualified:
            ident=row['id'];key=f's{seed}_{ident}';folder=out/'cells'/key;folder.mkdir(parents=True)
            for name in ('initial.json','baseline_full.json','baseline_binding.json'):
                shutil.copy2(out/'candidates'/ident/name,folder/name)
            native=ROOT/row['development']['measurement']
            records={k:read(native/k/'result.json') for k in ('alignment','search','history')}
            with patch.object(c,'SEED',seed):
                req=c.request(read(folder/'initial.json'),records,native,False,0)
                tests=c.controller_checks(req)
            assert set(json.loads(req['messages'][1]['content'])['actual_feedback']['visible_counts'])=={'alignment','search'}
            dump(folder/'request.preview.json',req);dump(folder/'controller_checks.json',tests)
            config=read(PREVIOUS/'model_config.json');config['options']['seed']=seed
            dump(folder/'model_config.json',config)
            cells.append(dict(id=key,candidate=ident,seed=seed,native=rel(native),behavior_profile=row['development']['behavior_profile'],
                              mechanisms=sorted(row['development']['strata']),request_sha256=digest(folder/'request.preview.json')))
    dump(out/'cells.json',cells)
    dump(out/'mechanisms.json',{k:dict(distinct_evidence_points=len(v),deduplication='obligation / first|first_held|later_held / trigger_state; no waveform variants counted as separate gaps') for k,v in mechanisms.items()})
    profiles={}
    for row in qualified:profiles.setdefault(row['development']['behavior_profile'],[]).append(row['id'])
    dump(out/'behavior_profiles.json',profiles)
    for rev in ('before','after'):shutil.copytree(PREVIOUS/rev,out/rev)
    shutil.copy2(PREVIOUS/'source_binding.json',out/'source_binding.json')
    protocol=dict(purpose=PURPOSE,created_at=time.time(),status='sealed_no_model_authorization',
        population=rel(out/'population_lock.json'),candidates=[r['id'] for r in qualified],seeds=list(SEEDS),cells=len(cells),
        distinct_observed_behavior_profiles=len(profiles),parent_count=1,
        common_generation='Frozen research142 label-bound text frontend, same model/temperature/output cap, decoded aid and evidence formatter. Same candidate sources, current9/search36 public inputs and complete151 gates. No new prompt repair or plan stage.',
        mechanism_scope='Generator/conditional historical recovery stability. All initial gaps are known development/public feedback, not new search discoveries. Behavioral duplicates clustered; text variants are not independent defects.',
        controller='Reuse research142.execute with only per-cell SEED and BASE_NATIVE bound; each cell starts from its own frozen initial candidate/ledger. Model output assembly, native evaluation and audit remain research139.',
        continuation='One shared proposal. Only O accepts, H rejects, confirmed regression and no critical unknown permits one H recovery. Otherwise stop that cell. No ordinary repair retry.',
        model=c.p.s.MODEL,endpoint=c.p.transport.DEFAULT_URL,temperature=0.2,max_output_tokens=1024,
        maximum_model_calls=2*len(cells),maximum_calls_per_cell=2,maximum_reserved_tokens=80000*len(cells),
        maximum_native_compiles=16*len(cells),maximum_native_executions=16*len(cells),
        maximum_wall_seconds=1200*len(cells),per_call_timeout_seconds=300,retries=0,
        stop='Fixed seed-major schedule. Transmission failure or execution/integrity exception stops the entire batch. Other protocol terminal branches stop only their cell. No replacement seed/candidate, quota transfer, repeated cell or automatic expansion.',
        independent='Defer ALL test generation until all cells terminal (including explicit not-run on global stop) and global final-version hashes frozen. Generate one shared new96-word/four-config batch; exclude all development and prior independent input words. Evaluate terminal O/H of cells with a new full-accepted H version. Deduplicate identical candidate hashes physically. No old independent outcomes read and no model call after tests.',
        metrics=dict(generation_acceptance='first full151 acceptance / first actual dispatches; also report planned coverage and ordinary acceptance; transport/interface failures retained',
            conditional_recovery='full151 recovered / qualified O-accept H-reject regression opportunities; 0 opportunities => null; report actual recovery attempts separately',
            independent_pass='H full-accepted terminal trial identities passing / full-accepted terminal trials scheduled for holdout; missing/failed execution not silently removed; also report unique version rates and whole-schedule success',
            grouping='candidate, requested seed, mechanism strata, observed behavior-profile cluster and parent. Correlated cells are not independent bugs; no cross-parent generalization.',
            unknown='Native/guard critical unknown, transport/native failure, not-run cells and unexposed obligation groups reported separately.',
            costs='Physical calls, known/unknown tokens, per-cell actual native time/commands, separate qualification cost, shared holdout dedup cost. Monetary charges unavailable.'),
        authorization='New explicit purpose/seal/output-bound grant required; research142 unused conditional call is not transferable.',
        research133='Not read; stays independent. No standalone search-advantage claim, no R-over-H uniqueness claim.')
    dump(out/'protocol.json',protocol)
    dump(out/'qualification.json',dict(passed=True,eligible=len(qualified),all_executable_candidates=len(rows),fifo_exclusions=len(fifo),
        raw_only_exclusions=len(raw_only),raw_development_rows_reaudited=read_rows,model_calls=0,new_native_calls=0,
        planned_cells=len(cells),behavior_profiles=len(profiles),independent_inputs_read=False))
    for row in rows:
        for source in row['sources']:bindings[source['path']]=source['sha256']
    for row in raw_only:bindings[row['path']]=row['sha256']
    for f in (ROOT/'scripts').glob('*.py'):bindings[rel(f)]=digest(f)
    bindings[rel(PREVIOUS/'sealed.json')]=digest(PREVIOUS/'sealed.json')
    dump(out/'source_bindings.json',bindings);dump(out/'read_audit.json',sorted(opened))
    dump(out/'sealed.json',{f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file()})
    verify(out)
    print('SEALED145',len(qualified),'candidates',len(profiles),'profiles',len(cells),'cells; model0',flush=True)


def verify(prep):
    for name,sha in read(prep/'sealed.json').items():assert digest(prep/name)==sha,name
    for name,sha in read(prep/'source_bindings.json').items():assert digest(ROOT/name)==sha,name
    for cell in read(prep/'cells.json'):
        folder=prep/'cells'/cell['id']
        assert digest(folder/'request.preview.json')==cell['request_sha256']
        with patch.object(c,'SEED',cell['seed']):assert c.controller_checks(read(folder/'request.preview.json'))==read(folder/'controller_checks.json')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','verify'))
    ap.add_argument('--out',type=Path);ap.add_argument('--prepared',type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:verify(a.prepared.resolve());print('VERIFIED145;model0')
