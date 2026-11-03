"""Reuse independent event/applicability validation before any SVA generation.

Only native development records are read during preparation. No old successful
plan or property is inserted. Two real plan attempts, then at most two SVA
attempts only if ALL independently certified window labels pass.
"""
import argparse
import copy
import json
from pathlib import Path
import random
import shutil
import research17_loop as loop
import research31_gate as history_gate
import research32_runtime as extension
import research43_paired_ablation as common
import research44_interface as interface
import research45_campaign as prior
from research34_applicability import certificate, PlanModel
from research36_applicability import validate_events
from research15_evidence import marker_map
from research35_campaign import holdout, join_results
from research17_report import cost_audit

ROOT=loop.ROOT
read,dump=loop.read,loop.dump
P43=interface.PREP
P45=ROOT/'deliverables/research45_prepare_20261022_r02'
R45=ROOT/'deliverables/research45_real_20261022_r01'
SEED=4601


def windows():
    cases=read(P45/'pilot/cases.json')
    baseline=prior.baseline(P45,'pilot')
    evidence=loop.inspect(baseline['group']['ledger'])
    selected=[];seen=set()
    def add(path,cycle,scenario,variant,category):
        path=history_gate.portable(path);key=(str(path),cycle)
        if key in seen:return
        truth=certificate(read(path),cycle)
        assert truth['applicability']!='unknown',category
        selected.append(dict(**truth,source=str(path),source_sha256=common.digest(path),
            scenario=scenario,variant=variant,category=category))
        seen.add(key)
    for key in sorted(evidence['misses']):
        row=evidence['rows'][key]
        assert row['obligation']=='stall_stability' and row['oracle']['paired_control_pass'] and row['oracle']['identical_input_handshakes']
        source=history_gate.portable(row['source_directory'])/'replay.json'
        add(source,row['cycle'],row['scenario_id'],row['variant'],'target:'+row['variant'])
        add(source.parent.parent/'correct/replay.json',row['cycle'],row['scenario_id'],'correct','paired_correct:'+row['variant'])
    # The exact legal transaction change misreported by research45. This is
    # development evidence, not a fresh independent test or an invented trace.
    add(R45/'pilot/core/v2/visible_native/case_2/correct/replay.json',15,
        cases[2]['id'],'correct','accepted_then_new_transaction')
    records=([(P43/'core/qualification/common/case_0/correct/replay.json',cases[0]['id'])]+
        [(P43/f's4211/core/qualification/acquired/case_{i}/correct/replay.json',c['id']) for i,c in enumerate(cases[1:])])
    found=set()
    for path,scenario in records:
        record=read(path)
        for previous,now in zip(record['trace'],record['trace'][1:]):
            truth=certificate(record,now['cycle']);label=truth['applicability'];kind=None
            if label=='cancelled':kind='reset_cancels_pending'
            elif label=='not_required':
                if previous['rst'] and not now['rst']:kind='reset_release'
                elif not previous['rst'] and not now['rst'] and not previous['mvalid']:kind='idle_no_pending'
                elif not previous['rst'] and not now['rst'] and previous['mvalid'] and previous['mready']:kind='accepted_no_hold'
            elif label=='required':kind='ready_rise_hold' if now['mready'] else 'continued_stall_hold'
            if kind and kind not in found:
                add(path,now['cycle'],scenario,'correct',kind);found.add(kind)
    assert found=={'reset_cancels_pending','reset_release','idle_no_pending','accepted_no_hold','ready_rise_hold','continued_stall_hold'},found
    random.Random(SEED).shuffle(selected)
    for i,truth in enumerate(selected):truth['id']=f'w{i}'
    public=[dict(id=t['id'],anchor_sample={k:t['samples'][0][k] for k in ('cycle','rst','mvalid','mready')},
        check_sample={k:t['samples'][1][k] for k in ('cycle','rst')}) for t in selected]
    return public,selected


def native_window_gate(folder,cases,candidate,edited_id,expected):
    """Bind MODEL-validated applicable windows to actual native cover samples.

    Required transitions must be covered by the edited property on its native
    antecedent edge. Nonrequired windows need not be untriggered, but must not
    produce a false alarm on independently satisfied hardware behavior.
    """
    index={c['id']:i for i,c in enumerate(cases)};cache={};checks=[];reasons=[]
    prop=next(a for a in candidate['assertions'] if a['id']==edited_id)
    for truth in expected:
        path=folder/f"case_{index[truth['scenario']]}"/truth['variant']/'replay.json'
        if path not in cache:cache[path]=read(path) if path.exists() else None
        record=cache[path];row=dict(id=truth['id'],source=str(path),label=truth['applicability'])
        if record is None:
            reasons.append(dict(kind='missing_native_window',id=truth['id']));checks.append(row);continue
        cert=certificate(record,truth['check_cycle'])
        same=all(cert.get(k)==truth[k] for k in ('anchor_cycle','check_cycle','applicability','samples','oracle_checks'))
        row.update(independent_certificate_unchanged=same,
            antecedent_cycle=truth['check_cycle']-prop['derived_delay'])
        if not same:reasons.append(dict(kind='window_unknown_or_changed',id=truth['id']))
        triggers=marker_map(record['native'],'triggers').get(edited_id,set())
        failures=marker_map(record['native'],'failures').get(edited_id,set())
        row.update(triggered=row['antecedent_cycle'] in triggers,failed=truth['check_cycle'] in failures)
        if truth['applicability']=='required' and not row['triggered']:
            reasons.append(dict(kind='validated_required_window_not_triggered',id=truth['id']))
        if record['mode']=='correct' and row['failed']:
            reasons.append(dict(kind='legal_window_false_alarm',id=truth['id']))
        checks.append(row)
    return dict(accepted=not reasons,reasons=reasons,windows=checks,
        scope='Native trigger/sample correspondence only; current target causal detection and full history are additional mandatory gates.')


class EventModel(PlanModel):
    def __init__(self,out,settings,payload):
        super().__init__(out,settings,payload)
        path=self.out/'remote_transport_config.json';meta=read(path);meta['max_output_tokens']=payload['max_tokens'];dump(path,meta)


def prepare(out):
    loop.prepare(out)
    initial=read(P45/'shared_initial.json');public,expected=windows()
    dump(out/'windows.public.json',public);dump(out/'expected.private.json',expected)
    dump(out/'shared_initial.json',initial)
    for name in ('history_cases','history_binding'):shutil.copy2(P45/(name+'.json'),out/(name+'.json'))
    dump(out/'cases.json',read(P45/'pilot/cases.json'))
    dump(out/'baseline_binding.json',read(P45/'pilot/baseline_binding.json'))
    dump(out/'excluded_tests.json',dict(input_hashes=sorted(prior.extra_exclusions())))
    dump(out/'protected.json',common.protected())
    previous_request=read(P45/'pilot/request.preview.json')
    body=json.loads(previous_request['messages'][1]['content'])
    # Reuse the published event semantics and strict validator, not an old
    # successful model answer, old SVA or complete private certificate table.
    old_events=json.loads(read(ROOT/'deliverables/research36_prepare_20261022_r01/request.preview.json')['messages'][1]['content'])['event_semantics']
    plan_body=dict(task='Identify the causal output event and when its stall_stability obligation applies. Do not generate SVA.',
        rtl_and_common_contract=body['rtl_and_common_contract'],event_semantics=old_events,windows=public,
        projection='Only observed causal samples are shown. No current output validity, payload, private expected labels or assertion text is supplied.',
        response_schema=dict(windows=[dict(id='given id',anchor_cycle='integer',check_cycle='integer',pending='boolean',reset='boolean',applicability=['required','cancelled','not_required','unknown'])]),
        validation='Every boolean, cycle and label must match independent native transaction/reset records; unknown, missing or inconsistent answers stop before SVA. No field is corrected for you.')
    request=copy.deepcopy(previous_request);request.update(seed=SEED,max_tokens=2048)
    request['messages']=[dict(role='system',content='Identify hardware obligation applicability from causal sampled events and specification. Return the exact JSON event plan, no SVA.'),dict(role='user',content=json.dumps(plan_body))]
    dump(out/'plan_request.preview.json',request)
    diagnostic=read(R45/'pilot/core/v2/next_feedback.json')
    sva=prior.request_from(previous_request,initial,SEED,diagnostic)
    dump(out/'sva_request.template.json',sva)
    dump(out/'source_binding.json',dict(prior_native_failure=str(R45/'pilot/core/v2'),diagnostic_sha256=common.digest(R45/'pilot/core/v2/next_feedback.json'),
        reused_validator='research36_applicability.validate_events',old_model_plan_reused=False,old_successful_sva_reused=False))
    fixture=dict(windows=[])
    for t in expected:
        p,n=t['samples'];fixture['windows'].append(dict(**{k:t[k] for k in ('id','anchor_cycle','check_cycle','applicability')},
            pending=bool(not p['rst'] and p['mvalid'] and not p['mready']),reset=bool(n['rst'])))
    checks=[]
    def test(name,value,want):
        verdict=validate_events(value,expected)
        checks.append(dict(name=name,passed=verdict['accepted']==want));assert checks[-1]['passed'],name
    test('oracle_fixture_not_model',fixture,True)
    for index,row in enumerate(fixture['windows']):
        for field in ('pending','reset'):
            bad=copy.deepcopy(fixture);bad['windows'][index][field]=not row[field]
            test(f"{row['id']}:wrong_{field}",bad,False)
    for kind in ('missing','duplicate','unknown','wrong_cycle','non_boolean'):
        bad=copy.deepcopy(fixture)
        if kind=='missing':bad['windows'].pop()
        elif kind=='duplicate':bad['windows'].append(copy.deepcopy(bad['windows'][0]))
        elif kind=='unknown':bad['windows'][0]['applicability']='unknown'
        elif kind=='wrong_cycle':bad['windows'][0]['check_cycle']+=1
        else:bad['windows'][0]['pending']=1
        test(kind,bad,False)
    negative=native_window_gate(R45/'pilot/core/v2/visible_native',read(out/'cases.json'),
        read(R45/'pilot/core/v2/model_call/candidate.json'),'a4',expected)
    assert not negative['accepted'] and any(r['kind']=='validated_required_window_not_triggered' for r in negative['reasons'])
    assert any(r['kind']=='legal_window_false_alarm' for r in negative['reasons'])
    dump(out/'known_failed_property_window_gate.json',negative)
    for bad in (None,dict(windows=[])):
        try:verified_sva_request(sva,bad,validate_events(bad,expected),expected)
        except AssertionError:checks.append(dict(name='failed_plan_blocks_sva_request',passed=True))
        else:raise AssertionError('SVA_request_created_before_event_acceptance')
    checked=validate_events(fixture,expected)
    guarded=verified_sva_request(sva,fixture,checked,expected)
    assert json.loads(guarded['messages'][1]['content'])['verified_model_applicability_plan']==fixture
    checks.append(dict(name='passed_validator_fixture_unlocks_only_local_payload_not_model_success',passed=True))
    assert 'applicability' not in public[0] and all('mvalid' not in w['check_sample'] for w in public)
    assert not any(t['source'] in json.dumps(request) for t in expected)
    dump(out/'qualification.json',dict(passed=True,checks=checks,windows=len(expected),model_calls=0,new_native_calls=0,
        scope='Actual native development record reuse and independent validator fixtures; not a model plan success.',
        categories=[t['category'] for t in expected],old_property_rejected_on_actual_native_records=True))
    dump(out/'protocol.json',dict(max_calls=4,max_plan_calls=2,max_sva_calls=2,seed=SEED,temperature=0.2,max_output_tokens=2048,retries=0,
        endpoint=prior.settings(SEED,2)['remote_url'],model=prior.settings(SEED,2)['remote_model'],
        order='All events/cycles/applicability labels independently pass before any SVA call. Then native window coverage, current targets and105 history. Freeze accepted new version then fresh56 holdout. Stop on failure, unknown or budget.',
        data='All research45 evidence remains development. No independent test or successful SVA/plan in prompts. Only passed actual model plan enters SVA generation.',
        authorization='Requires explicit reassignment of4 of research45 unused8 conditional-ablation calls; no implicit transfer.',
        scope='Selected artificial-fault FIFO development windows, not a general understanding test or mechanism ablation.'))
    common.snapshot(out)
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():common.digest(p) for p in common.files(out)
        if p.suffix=='.json' and 'source_snapshot' not in p.parts})
    print('CYCLE_GATE_PREPARED',len(expected),'windows',len(checks),'checks',flush=True)


def bound_baseline(prep):
    binding=read(prep/'baseline_binding.json');parts=[]
    for name in ('common','target'):
        path=history_gate.portable(binding[name]);assert common.digest(path)==binding[name+'_sha256'];parts.append(read(path))
    return join_results(parts)


def verified_sva_request(template,plan,verdict,expected):
    # Executable guard: no SVA payload can be made from a failed or stale plan.
    checked=validate_events(plan,expected)
    assert checked['accepted'] and verdict==checked,'applicability_not_accepted'
    request=copy.deepcopy(template);body=json.loads(request['messages'][1]['content'])
    body['verified_model_applicability_plan']=plan
    body['stage_contract']='Your event claims, cycles and labels passed the independent native transaction/reset gate. Generate an AST whose native trigger sample covers every required transition, including paired legal controls; do not narrow away the check when the output is wrong. Non-required windows may trigger only without false alarms. Native execution, not wording, decides acceptance.'
    request['messages'][1]['content']=json.dumps(body)
    return request


def run(prep,out,authorization):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==4 and auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    common.check_sources(prep)
    loop.prepare(out);common.snapshot(out);shutil.copy2(authorization,out/'authorization.json');shutil.copy2(prep/'protocol.json',out/'protocol.json')
    dump(out/'prepared_source.json',dict(path=str(prep)))
    initial=current=read(prep/'shared_initial.json');expected=read(prep/'expected.private.json')
    models=[];status='running';accepted_plan=None;accepted=False
    try:
        model=EventModel(out/'plan/model',prior.settings(SEED,2),read(prep/'plan_request.preview.json'));models.append(model)
        for i in range(2):
            folder=out/'plan'/f'v{i}'
            call,plan=model.call(folder/'model_call',initial,'stall_stability',{},'event_applicability_before_sva')
            verdict=validate_events(plan,expected);dump(folder/'decision.json',verdict)
            print('PLAN',i,'accepted',verdict['accepted'],'reasons',len(verdict['reasons']),flush=True)
            if verdict['accepted']:accepted_plan=plan;break
            body=json.loads(model.payload['messages'][1]['content'])
            body.update(prior_actual_model_plan=plan,prior_actual_rejection=verdict['reasons'])
            model.payload['messages'][1]['content']=json.dumps(body)
        if accepted_plan is None:status='applicability_rejected_no_sva';return
        dump(out/'accepted_plan.json',accepted_plan);dump(out/'accepted_plan_gate.json',verdict)
        template=read(prep/'sva_request.template.json')
        request=verified_sva_request(template,accepted_plan,verdict,expected)
        model=prior.Model(out/'sva/model',prior.settings(SEED,2),request);models.append(model)
        baseline=bound_baseline(prep);history=read(prep/'history_cases.json');cases=read(prep/'cases.json')
        binding=read(prep/'history_binding.json');history_path=history_gate.portable(binding['path'])
        assert common.digest(history_path)==binding['sha256'];historical=read(history_path)
        with extension.installed():
            for i in range(2):
                assert validate_events(accepted_plan,expected)['accepted']
                folder=out/'core'/f'v{i}'
                call,candidate=model.call(folder/'model_call',current,'stall_stability',{},'after_independent_event_gate')
                edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
                small=loop.replay(candidate,folder/'visible_native',cases) if candidate else None
                decision=common.current_decision(baseline,small,edit) if candidate else dict(accepted=False,reasons=[dict(kind='unusable_sva_output')])
                dump(folder/'current_gate.json',decision)
                window_gate=(native_window_gate(folder/'visible_native',cases,candidate,edit['assertion_id'],expected)
                    if candidate and small.get('group') and edit['operation']=='replace_one' else dict(accepted=False,reasons=[dict(kind='window_check_unavailable')]))
                dump(folder/'native_window_gate.json',window_gate)
                reasons=list(decision['reasons'])+window_gate['reasons'];full=None
                if decision['accepted'] and window_gate['accepted']:
                    full=loop.replay(candidate,folder/'history_native',history)
                    hgate=(history_gate.decide(historical['group']['ledger'],full['group']['ledger']) if full.get('group')
                        else dict(accepted=False,reasons=[dict(kind='history_unavailable')]))
                    dump(folder/'history_gate.json',hgate);reasons+=hgate['reasons']
                    if not full['healthy']:reasons.append(dict(kind='history_native_unhealthy'))
                accepted=bool(decision['accepted'] and window_gate['accepted'] and full and full['healthy'] and not reasons)
                final=dict(accepted=accepted,reasons=reasons);dump(folder/'decision.json',final)
                print('SVA',i,'accepted',accepted,'reasons',len(reasons),flush=True)
                if accepted:current=candidate;break
                diagnostic=prior.attempt_feedback(small,full,final,call,edit)
                diagnostic['validated_windows_native_rejection']=window_gate
                dump(folder/'next_feedback.json',diagnostic)
                updated=prior.request_from(template,initial,SEED,diagnostic)
                model.request=verified_sva_request(updated,accepted_plan,verdict,expected)
            loop.freeze(out/'core',current,'native_history_terminal_before_new_independent')
            if not accepted:status='event_passed_sva_rejected';return
            holdout(out,current,history+cases,set(read(prep/'excluded_tests.json')['input_hashes']))
            passed=read(out/'independent/summary.json')['all_five_pass_on_first_attributed_evidence']
            status='accepted_new_independent_passed' if passed else 'accepted_new_independent_failed'
    except BaseException:
        status='execution_exception';raise
    finally:
        if not (out/'core/freeze.json').exists():loop.freeze(out/'core',current,'retained_after_failed_event_or_sva_gate')
        dump(out/'outcome.json',dict(status=status,model_calls=sum(len(m.calls) for m in models),plan_passed=accepted_plan is not None,
            sva_accepted=accepted,frozen_hash=loop.sha(current),max_calls=4,prior_versions_unchanged=common.protected()==read(prep/'protected.json')))
        dump(out/'cost.json',cost_audit(out,common.files(out)))
        print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();assert ROOT in out.parents
    if a.action=='prepare':prepare(out)
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
