"""Pre-model qualification repair: loop.replay already executes the correct control.

Preserve research67 search and failed qualification. Use prepared_v4; no changes
to policy, seeds, interface, target selection, acceptance or call limits.
"""
import argparse
import json
from pathlib import Path
import time
import research67_controlled_campaign as base

ROOT,read,dump=base.ROOT,base.read,base.dump


def verify(root,prep):
    base.verify(root)
    for p,h in read(prep/'sealed.json').items():assert base.search.digest(prep/p)==h,p
    for p,h in read(prep/'code_versions.json').items():assert base.search.digest(ROOT/p)==h,p


def qualify(root,seed):
    base.verify(root)
    source=root/'search'/f's{seed}';dest=root/'prepared_v4'/f's{seed}'
    assert not dest.exists();dest.mkdir(parents=True)
    assert read(source/'outcome.json')['status']=='completed'
    public=read(source/'public_feedback.json')[base.PAIR_NAME]
    # Each non-correct case calls correct + mutant. Separate correct-mode cases
    # duplicate the same path in the old generic replay implementation.
    common_cases=[base.case_for(r,m,'public67') for r in public['results'] for m in base.search.MODES if m!='correct']
    selected=[];keys=set();bindings=[]
    for r in read(source/'records.json'):
        if r['method']!='contract_novelty':continue
        for gap in r['gaps']:
            if (gap['kind']=='FN' and gap['obligation']=='stall_stability' and gap['key'] not in keys
                    and gap['key'] not in public['gap_keys'] and len(keys)<2):
                keys.add(gap['key']);selected.append(base.case_for(r,gap['mode'],f'search67:s{seed}'))
                bindings.append(dict(key=gap['key'],query=r['query'],evidence_id=gap['evidence']['evidence_id'],
                    replay_source=gap['replay_source'],validation=gap['validation'],trigger_class=gap['trigger_class']))
    dump(dest/'selected.json',dict(keys=sorted(keys),bindings=bindings,not_global_novelty=True))
    dump(dest/'pre_model_amendment.json',dict(at=time.time(),parent_protocol_sha256=base.search.digest(root/'protocol.json'),
        failed_preparation=str(root/'prepared'/f's{seed}'),
        correction='Exclude separate correct-mode cases from generic loop.replay; every fault case still runs the identical correct control. Original 16-run public search qualification is unchanged.',
        adapter_corrections='Keep fault extension installed while projecting requests. Store development native replay under core as required by the existing strict development-only trace reader; do not relax its independent-data guard.',
        search_results_reused=True,search_rerun=False,public_mutant_cases=14,public_correct_replays=14,
        algorithm_or_acceptance_change=False,model_calls_before_amendment=0,
        old_failure_preserved=True,source_sha256=base.search.digest(Path(__file__))))
    if not selected:
        dump(dest/'qualification.json',dict(passed=False,reason='no_public_unexposed_contract_stall_witness'));return
    for n in ('shared_initial.json','history_cases.json','history_binding.json'):dump(dest/n,read(root/n))
    initial=read(dest/'shared_initial.json')
    dump(dest/'common_cases.json',common_cases);dump(dest/'search_cases.json',selected)
    with base.extension.installed():
        common=base.loop.replay(initial,dest/'core/native/common',common_cases)
        target=base.loop.replay(initial,dest/'core/native/search',selected)
    okay=all(r['healthy'] and not r['counts']['false_positives'] and not r['counts']['unknown'] for r in (common,target)) and target['counts']['misses']>=len(selected)
    if okay:
        for stream,use_search in (('ordinary',False),('search',True)):
            visible=base.join_results([common,target]) if use_search else common
            feedback=dict(requested_obligations=['stall_stability'],counts=visible['counts'],actual_native_evidence=visible['feedback'],
                ordinary_observations=dict(scenario='public67',counts=common['counts'],native_diagnostic=common['feedback']))
            # The real payload projector also resolves the fault-mode registry;
            # retain the same installed extension during request construction.
            with base.extension.installed():
                req=base.paired.payload(dest/stream/'preview',initial,feedback,seed)
            req=base.campaign.request_from(req,initial,seed)
            dump(dest/stream/'request.preview.json',req)
            dump(dest/stream/'cases.json',common_cases+(selected if use_search else []))
            dump(dest/stream/'baseline_binding.json',dict(common=str(dest/'core/native/common/result.json'),
                common_sha256=base.search.digest(dest/'core/native/common/result.json'),
                target=str(dest/'core/native/search/result.json') if use_search else None,
                target_sha256=base.search.digest(dest/'core/native/search/result.json') if use_search else None))
        a=read(dest/'ordinary/request.preview.json');b=read(dest/'search/request.preview.json')
        aa=json.loads(a['messages'][1]['content']);bb=json.loads(b['messages'][1]['content'])
        for k in ('rtl_and_common_contract','confirmed_obligations','current_assertions','output_schema','temporal_semantics','ordinary_observations'):assert aa[k]==bb[k],k
        assert all(c['id'] not in json.dumps(a) for c in selected)
        assert all('research63' not in json.dumps(r) and 'verified_model_applicability_plan' not in json.dumps(r) for r in (a,b))
        dump(dest/'request_metadata.json',{s:dict(bytes=len(json.dumps(read(dest/s/'request.preview.json')).encode()),
            sha256=base.search.digest(dest/s/'request.preview.json')) for s in ('ordinary','search')})
    dump(dest/'qualification.json',dict(passed=okay,common=common['counts'],target=target['counts'],selected_gaps=len(keys),
        shared_helpers_equal=okay,search_isolated=okay,model_calls=0,credentials_read=False))
    dump(dest/'cost.json',base.search.native_cost(dest))
    dump(dest/'code_versions.json',{p.relative_to(ROOT).as_posix():base.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(dest/'sealed.json',{p.relative_to(dest).as_posix():base.search.digest(p) for p in dest.rglob('*.json') if 'obj_dir' not in p.parts})
    print('QUALIFIED_V2',seed,okay,'common',common['counts'],'target',target['counts'],flush=True)


def exclusions(root):
    values,sources=base.exclusions(root)
    # Cover every historical candidate-pair query, not only the bounded peer.
    for name in ('research64_search_value_20261023_r01','research65_search_value_20261024_r01'):
        for p in (ROOT/'deliverables'/name).glob('**/correct_stimulus/stimulus.json'):
            v=read(p);values.add(base.loop.sha(v['rows'] if isinstance(v,dict) else v))
    return values,sources


def pilot(root,authorization):
    prep=root/'prepared_v4'/f's{base.PILOT}';out=root/'pilot_run'
    verify(root,prep);assert read(prep/'qualification.json')['passed']
    auth=read(authorization);protocol=read(root/'protocol.json')
    assert auth['authorized_calls']==3 and auth['purpose']=='research67_pilot'
    assert auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['protocol_sha256']==base.search.digest(root/'protocol.json')
    assert auth['preparation_sha256']==base.search.digest(prep/'sealed.json')
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    assert not out.exists();out.mkdir(parents=True)
    dump(out/'authorization.json',auth)
    budget=dict(reserved=0,maximum=3,path=out/'attempt_budget.json');models=[];passed=False;status='running'
    try:
        with base.extension.installed():
            candidate,result=base.run_arm(prep,out/'refinement','search',base.PILOT,3,True,budget,models)
            if not result['accepted'] or not result['new_executable_version']:
                status='pilot_refinement_failed_stop_before_multiseed';return
            excluded,sources=exclusions(root)
            development=read(prep/'history_cases.json')+read(prep/'common_cases.json')+read(prep/'search_cases.json')
            dump(out/'exclusion_manifest.json',dict(input_hashes=sorted(excluded|{base.loop.sha(c['rows']) for c in development}),sources=sources))
            base.holdout(out/'refinement',candidate,development,excluded)
            passed=read(out/'refinement/independent/summary.json')['all_five_pass_on_first_attributed_evidence']
            status='pilot_passed_multiseed_still_requires_separate_grant' if passed else 'pilot_independent_failed_stop_before_multiseed'
    except BaseException as exc:
        status='execution_exception';dump(out/'exception.json',dict(error=repr(exc)));raise
    finally:
        verify(root,prep)
        dump(out/'outcome.json',dict(status=status,pilot_passed=passed,calls=sum(len(m.calls) for m in models),reserved=budget['reserved']))
        dump(out/'cost.json',base.search.native_cost(out))
        print('PILOT',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('qualify','pilot'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=base.PILOT);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='qualify':qualify(a.out.resolve(),a.seed)
    else:pilot(a.out.resolve(),a.authorization.resolve())
