"""Real SVA continuation from the accepted research47 sample-bound plan.

No event-model calls, answer substitution, or independent-test feedback. Every
native-admitted proposal is evaluated on current evidence and105 history cases.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil

import research17_loop as loop
import research31_gate as gate
import research32_runtime as runtime
import research43_paired_ablation as common
import research44_interface as interface
import research45_campaign as prior
import research46_cycle_gate as windows
import research47_sample_binding as plan_gate
from research17_report import cost_audit
from research28_report import raw_response

ROOT=loop.ROOT
read,dump=loop.read,loop.dump
P46=ROOT/'deliverables/research46_prepare_20261022_r01'
P47=ROOT/'deliverables/research47_prepare_20261022_r01'
R47=ROOT/'deliverables/research47_real_20261022_r01'
MAX_CALLS=3


def accepted_plan(prep):
    binding=read(prep/'plan_binding.json')
    for path,h in binding['files'].items():
        assert common.digest(gate.portable(path))==h,'changed_plan_source'
    plan=read(prep/'accepted_plan.json');expected=read(prep/'expected.private.json')
    assert plan==read(R47/'accepted_plan.json')
    assert raw_response(R47/'plan/v0/model_call',plan),'plan_not_actual_response'
    verdict=plan_gate.validate(plan,expected)
    assert verdict['accepted'] and verdict==read(prep/'accepted_plan_gate.json')
    return plan,expected,verdict


def history_source(prep):
    binding=read(prep/'history_binding.json');path=gate.portable(binding['path'])
    assert common.digest(path)==binding['sha256']
    value=read(path)
    assert value['healthy'] and not any(value['counts'][k] for k in ('misses','false_positives','unknown'))
    return value


def mapping(result):
    if not result or not result.get('group'):return dict(status='unavailable')
    info=loop.inspect(result['group']['ledger'])
    return dict(status='measured',obligations=info['mapping'],unknown_evidence=sorted(info['unknown']),
        scope='Per-obligation native trigger/detection links on replayed evidence only; ledger exclusions remain unknown, not passes.',
        counts=result['counts'])


def build_feedback(small,full,decision,call,edit,previous_edit,window,last_native_feedback=None):
    """Keep the latest measured native rejection across a no-candidate call.

    The retained record is explicitly separate: it is not evidence of a native
    execution for the failed transport/schema attempt. No predicate is repaired.
    """
    diagnostic=prior.attempt_feedback(small,full,decision,call,edit,previous_edit)
    diagnostic['validated_windows_native_rejection']=window
    if (not small or not small.get('group')) and last_native_feedback is not None:
        diagnostic['retained_actual_native_feedback']=copy.deepcopy(last_native_feedback)
        diagnostic['retention_scope']='Prior actually executed development attempt only; this unusable-output attempt produced no new native evidence.'
    return diagnostic


def evaluate(candidate,edit,folder,prep,before,historical,expected,repeated=False):
    small=loop.replay(candidate,folder/'visible_native',read(prep/'cases.json')) if candidate else None
    current=common.current_decision(before,small,edit) if candidate else dict(accepted=False,reasons=[dict(kind='unusable_model_output')])
    window=(windows.native_window_gate(folder/'visible_native',read(prep/'cases.json'),candidate,edit['assertion_id'],expected)
        if candidate and small.get('group') and edit['operation']=='replace_one'
        else dict(accepted=False,reasons=[dict(kind='native_window_check_unavailable')]))
    # Compile failures cannot enter history. Legal-control failures still do: their
    # native evidence is useful rejection feedback, never a license to accept.
    full=loop.replay(candidate,folder/'history_native',read(prep/'history_cases.json')) if candidate and small.get('group') else None
    history=(gate.decide(historical['group']['ledger'],full['group']['ledger']) if full and full.get('group')
        else dict(accepted=False,reasons=[dict(kind='history_unavailable')]))
    reasons=list(current['reasons'])+window['reasons']+history['reasons']
    if not full or not full['healthy']:reasons.append(dict(kind='history_native_unhealthy'))
    if repeated:reasons.append(dict(kind='repeated_previously_rejected_executable'))
    final=dict(accepted=bool(current['accepted'] and window['accepted'] and history['accepted'] and full and full['healthy'] and not reasons),
        reasons=reasons,history_scenarios_expected=105,
        scope='Current development targets and105 historical scenarios only; no global guarantee or independent acceptance.')
    for name,value in [('current_gate',current),('native_window_gate',window),('history_gate',history),('decision',final)]:dump(folder/(name+'.json'),value)
    dump(folder/'obligation_mapping.json',dict(current=mapping(small),history=mapping(full)))
    return small,full,final,window


def prepare(out):
    loop.prepare(out)
    for name,source in [('shared_initial.json',P47),('expected.private.json',P47),('cases.json',P46),
            ('baseline_binding.json',P46),('history_cases.json',P46),('history_binding.json',P46),
            ('accepted_plan.json',R47),('accepted_plan_gate.json',R47)]:shutil.copy2(source/name,out/name)
    protected47={str(p):common.digest(p) for p in common.files(R47)}
    dump(out/'plan_binding.json',dict(files=protected47,raw_response='research47/plan/v0',old_plan_relabelled=False))
    dump(out/'protected.json',common.protected())
    plan,expected,verdict=accepted_plan(out)
    template=read(R47/'gated_sva_request.preview.json')
    assert template==plan_gate.verified_sva_request(read(P47/'sva_request.template.json'),plan,verdict,expected)
    dump(out/'request.preview.json',template)
    assert len(read(out/'history_cases.json'))==105
    historical=history_source(out);baseline=windows.bound_baseline(out)
    checks=[]
    def check(name,okay):
        checks.append(dict(name=name,passed=bool(okay)));assert okay,name
    check('actual_plan_all_fields_revalidated',verdict['accepted'])
    check('exact_already_gated_request',template==read(R47/'gated_sva_request.preview.json'))
    check('105_history_baseline_qualified',historical['healthy'])
    check('two_independent_targets',len(loop.inspect(baseline['group']['ledger'])['misses'])==2)
    initial=read(out/'shared_initial.json')
    with runtime.installed():
        fresh=loop.replay(initial,out/'core/initial_native',read(out/'cases.json'))
        check('initial_native_healthy',fresh['healthy'])
        old_info=loop.inspect(baseline['group']['ledger']);new_info=loop.inspect(fresh['group']['ledger'])
        check('fresh_targets_identical',old_info['misses']==new_info['misses'])
        check('fresh_identity_and_prior_protection',gate.decide(baseline['group']['ledger'],fresh['group']['ledger'])['accepted'])
        # Exact prior real model proposals are LOCAL gate controls only. Neither
        # the successful property nor any test data is added to the request.
        control_paths={
            'known_rejected':ROOT/'deliverables/research45_real_20261022_r01/pilot/core/v2/model_call/candidate.json',
            'archived_accepted':ROOT/'deliverables/research41_real_20261022_r01/s4103/core/frozen_candidate.json'}
        controls=[]
        for name,path in control_paths.items():
            candidate=read(path);folder=out/'core'/name
            changed=[a['id'] for a in candidate['assertions']
                if a['property']!=next(b for b in initial['assertions'] if b['id']==a['id'])['property']]
            assert len(changed)==1,'local_control_must_be_one_actual_edit'
            edited_id=changed[0]
            replay=loop.replay(candidate,folder/'native',read(out/'cases.json'))
            decision=common.current_decision(fresh,replay,dict(operation='replace_one',assertion_id=edited_id))
            native_windows=windows.native_window_gate(folder/'native',read(out/'cases.json'),candidate,edited_id,expected)
            dump(folder/'current_gate.json',decision);dump(folder/'native_window_gate.json',native_windows)
            controls.append(dict(name=name,source=str(path),source_sha256=common.digest(path),
                actual_changed_assertion=edited_id,
                current_accepted=decision['accepted'],windows_accepted=native_windows['accepted'],counts=replay.get('counts'),
                scope='Archived real candidate local regression only; not new model generation or current full-history acceptance.'))
            if name=='known_rejected':
                check('old_invalid_proposal_rejected_natively',not decision['accepted'] and not native_windows['accepted'])
                check('old_invalid_required_window_not_triggered',any(r['kind']=='validated_required_window_not_triggered' for r in native_windows['reasons']))
            else:
                check('archived_control_actual_edit_passes_current_and_windows',decision['accepted'] and native_windows['accepted'])
            print('CONTROL',name,'current',decision['accepted'],'windows',native_windows['accepted'],flush=True)
    dump(out/'local_controls.json',controls)
    for bad in (None,dict(windows=[])):
        try:plan_gate.verified_sva_request(template,bad,dict(accepted=True),expected)
        except ValueError:check('bad_plan_blocks_sva_payload',True)
        else:raise AssertionError('failed_plan_unlocked_sva')
    check('plan47_artifacts_unchanged',all(common.digest(gate.portable(p))==h for p,h in protected47.items()))
    check('old_frozen_versions_unchanged',read(out/'protected.json')==common.protected())
    dump(out/'qualification.json',dict(passed=all(c['passed'] for c in checks),checks=checks,
        model_calls=0,control_scope='Three native replay groups; prior candidates not model proposals for this run.'))
    dump(out/'protocol.json',dict(stage='sva_only_after_actual_accepted_plan',max_calls=MAX_CALLS,plan_calls=0,
        endpoint=prior.settings(windows.SEED,MAX_CALLS)['remote_url'],model=template['model'],
        seed=template['seed'],temperature=template['temperature'],max_tokens=template['max_tokens'],retries=0,
        acceptance='Native current targets, all11 required/legal windows,105 scenario history and trigger retention all pass; any critical unknown, repeated rejected executable or false positive rejects.',
        iteration='At most3 real SVA edits. Same previous accepted set retained on rejection. Only actual current/history/window diagnoses feed next round. Stop on first acceptance.',
        feedback_revision='retain_native_on_unusable_output_v1',
        interface='Reuse existing replace_one/keep AST interface and multi-SVA set. No complementary-add operation introduced in this bounded trial.',
        history='Run105 history scenarios for each native-admitted proposal even when current target gate fails, to expose real regression diagnostics.',
        independence='Development acceptance only. Freeze terminal candidate; new independent tests are a later task and are not sent to model.',
        authorization='Requires explicit reassignment/new SVA call budget; research47 unused1 is plan-only; research45 other4 conditional-ablation calls not automatically reusable.',
        provenance='Actual axis_fifo RTL plus explicit artificial boundary faults; not original historical bug reproduction.'))
    common.snapshot(out)
    dump(out/'cost.json',cost_audit(out,common.files(out)))
    (out/'SUMMARY.md').write_text('# research48 SVA continuation preparation\n\n'
        f'{len(checks)} local checks passed. Actual accepted research47 plan revalidated. '
        'Two current misses replayed on native FIFO; old real model candidates used only as local gate controls. '
        'No new remote generation, new SVA acceptance or independent test yet.\n\n'
        'Request: request.preview.json. Controls: local_controls.json. Cost: cost.json. '
        'Pending explicit SVA budget; at most3 calls, no retries, accept-and-stop.\n',encoding='utf-8')
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():common.digest(p) for p in common.files(out)
        if p.suffix=='.json' and 'source_snapshot' not in p.parts})
    print('SVA_PREPARED',len(checks),'checks; model_calls=0',flush=True)


def run(prep,out,authorization):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert 1<=auth['authorized_sva_calls']<=MAX_CALLS and auth['authorized_plan_calls']==0
    assert auth['scope']=='research48_sva_only' and auth['user_answer']
    assert auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    assert auth['prepared_request_sha256']==common.digest(prep/'request.preview.json')
    common.check_sources(prep);plan,expected,verdict=accepted_plan(prep)
    historical=history_source(prep);before=read(prep/'core/initial_native/result.json')
    initial=current=read(prep/'shared_initial.json');template=read(prep/'request.preview.json')
    loop.prepare(out);common.snapshot(out);dump(out/'protocol.json',protocol)
    shutil.copy2(authorization,out/'authorization.json');dump(out/'prepared_source.json',dict(path=str(prep)))
    model=prior.Model(out/'model',prior.settings(windows.SEED,auth['authorized_sva_calls']),template)
    accepted=False;status='running';rejected=set();previous_edit=None;trajectory=[]
    last_native_feedback=json.loads(template['messages'][1]['content']).get('actual_previous_attempt')
    try:
        with runtime.installed():
            for i in range(auth['authorized_sva_calls']):
                accepted_plan(prep)
                folder=out/'core'/f'v{i}'
                call,candidate=model.call(folder/'model_call',current,'stall_stability',{},'after_research47_event_acceptance')
                edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
                key=interface.executable_hash(candidate) if candidate else None
                repeated=bool(key and key in rejected)
                small,full,decision,window=evaluate(candidate,edit,folder,prep,before,historical,expected,repeated)
                trajectory.append(dict(iteration=i,candidate_hash=loop.sha(candidate) if candidate else None,executable_hash=key,
                    repeated_rejected_executable=repeated,accepted=decision['accepted'],reason_kinds=sorted({r['kind'] for r in decision['reasons']}),
                    current_counts=small.get('counts') if small else None,history_counts=full.get('counts') if full else None))
                dump(out/'trajectory.json',trajectory)
                print('SVA',i,'accepted',decision['accepted'],'reason_kinds',trajectory[-1]['reason_kinds'],flush=True)
                if decision['accepted']:current=candidate;accepted=True;break
                if key:rejected.add(key)
                diagnostic=build_feedback(small,full,decision,call,edit,previous_edit,window,last_native_feedback)
                diagnostic['repeated_previously_rejected_executable']=repeated
                if small and small.get('group'):last_native_feedback=copy.deepcopy(diagnostic)
                dump(folder/'next_feedback.json',diagnostic)
                updated=prior.request_from(template,current,windows.SEED,diagnostic)
                model.request=plan_gate.verified_sva_request(updated,plan,verdict,expected)
                previous_edit=edit
        status='accepted_development_history_pending_independent' if accepted else 'sva_rejected_previous_version_retained'
    except BaseException:
        status='execution_exception';raise
    finally:
        loop.freeze(out/'core',current,'complete_development_gate_passed' if accepted else 'rejected_versions_retained_previous_accepted_set')
        dump(out/'outcome.json',dict(status=status,accepted=accepted,model_calls=len(model.calls),plan_calls=0,
            frozen_hash=loop.sha(current),independent_test_run=False,prior_versions_unchanged=common.protected()==read(prep/'protected.json')))
        dump(out/'cost.json',cost_audit(out,common.files(out)))
        print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',required=True,type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args();out=a.out.resolve();assert ROOT in out.parents
    if a.action=='prepare':prepare(out)
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
