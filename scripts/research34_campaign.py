"""Two gated real calls: label applicability, then generate SVA if labels pass.

prepare executes archived controls only. run requires a new explicit two-call
grant, stops on failed applicability/target gate, and never rewrites expressions.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import research17_loop as loop
import research32_runtime as extension
import research31_gate as gate
from research32_campaign import initial_feedback
from research34_applicability import (build_windows,validate_plan,plan_request,PlanModel,
    VerifiedPlanModel,native_target_gate,portable)
from research17_report import artifacts,cost_audit

read,dump=loop.read,loop.dump
PREP=loop.ROOT/'deliverables/research33_prepare_20261021_r02'
OLD=loop.ROOT/'deliverables/research33_real_20261021_r01'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot(out):
    for p in (loop.ROOT/'scripts').glob('research*.py'):
        shutil.copy2(p,out/'source_snapshot'/p.name)
    dump(out/'source_snapshot/hashes.json',{p.name:digest(p) for p in (out/'source_snapshot').glob('*.py')})


def prepare(out):
    loop.prepare(out);snapshot(out)
    baseline_path=PREP/'local_controls/core/before/result.json';baseline=read(baseline_path)
    initial=read(PREP/'shared_initial.json');cases=read(PREP/'local_controls/cases.json')
    windows,expected=build_windows(baseline)
    dump(out/'windows.public.json',windows);dump(out/'applicability.expected.private.json',expected)
    dump(out/'shared_initial.json',initial);dump(out/'target_cases.json',cases)
    dump(out/'baseline_binding.json',dict(path=str(baseline_path),sha256=digest(baseline_path),cases_hash=loop.sha(cases),candidate_hash=loop.sha(initial)))
    settings=read(PREP/'s3203/model_config.json');settings['max_model_calls']=1
    dump(out/'model_config.json',settings)
    preview=plan_request(read(PREP/'s3203/preview/request.preview.json'),windows)
    dump(out/'plan_request.preview.json',preview)
    # Oracle answers are local test fixtures, never a generated model plan.
    fixture=dict(windows=[{k:r[k] for k in ('id','anchor_cycle','check_cycle','applicability')} for r in expected])
    tests=[]
    verdict=validate_plan(fixture,expected);assert verdict['accepted']
    tests.append(dict(name='oracle_fixture_positive_not_model',decision=verdict))
    for name in ('wrong_anchor','all_required','unknown','missing_window','wrong_reset_label'):
        value=copy.deepcopy(fixture)
        if name=='wrong_anchor':value['windows'][0]['anchor_cycle']+=1
        elif name=='all_required':
            for r in value['windows']:r['applicability']='required'
        elif name=='unknown':value['windows'][0]['applicability']='unknown'
        elif name=='missing_window':value['windows'].pop()
        else:
            next(r for r in value['windows'] if r['applicability']=='cancelled')['applicability']='required'
        decision=validate_plan(value,expected);assert not decision['accepted']
        tests.append(dict(name=name,decision=decision))
    dump(out/'local_plan_gate_tests.json',tests)
    # Exercise the shared output hook without transport, clearly not a model call.
    model=PlanModel(out/'local_plan_output_hook',settings,preview)
    model.save_decoded_output(out/'local_plan_output_hook',fixture,initial,'unused_test_secret')
    assert not (out/'local_plan_output_hook/candidate.sva').exists()
    controls=[]
    with extension.installed():
        sources=(('archived_bad',OLD/'s3203/core/v0/model_call/candidate.json','a4',False),
                 ('archived_good',loop.ROOT/'deliverables/research32_real_20261021_r01/s3209/core/frozen_candidate.json','a2',True))
        for name,path,edited,accepted in sources:
            candidate=read(path);result=loop.replay(candidate,out/'local_controls/core'/name,cases)
            decision=native_target_gate(baseline,result,edited)
            dump(out/'local_controls'/f'{name}_gate.json',decision)
            assert decision['accepted']==accepted,(name,decision)
            controls.append(dict(name=name,source=str(path),sha256=digest(path),decision=decision,counts=result['counts']))
    dump(out/'qualification.json',dict(passed=True,plan_tests=tests,native_controls=controls,model_calls=0,
        scope='Plan labels are unit-test fixtures, not LLM outputs; native controls are archived real model proposals, not new refinement.'))
    protocol=dict(maximum_calls=2,stage1_calls=1,stage2_calls=1,retries=0,endpoint=settings['remote_url'],model=settings['remote_model'],
        plan_preview_sha256=digest(out/'plan_request.preview.json'),source_hashes=read(out/'source_snapshot/hashes.json'),
        gates=['model applicability vs independent oracle','native target trigger and causal detection','complete history replay','freeze then new independent replay'],
        stage2_request='Created only after stage1 passed; same prepared development/RTL context plus exact actual verified model plan. No correct SVA is inserted.',
        stop='Any failed or unknown applicability check stops before SVA generation. Failed native target gate stops before complete history.',
        scope='Single failed seed 3203, actual axis_fifo with explicit artificial faults; not historical upstream fix or unbiased mechanism comparison.',
        historical_holdouts='All previously published tests are development knowledge; none used in these prompts. Future new holdouts created only after acceptance/freeze.')
    dump(out/'protocol.json',protocol)
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():digest(p) for p in out.glob('*.json')})
    cost=cost_audit(out,artifacts(out));dump(out/'local_cost.json',cost)
    (out/'SUMMARY.md').write_text('# research34：先核验义务适用周期，再核验原生性质\n\n'
        f'本地准备完成。{len(windows)} 个真实开发窗口；1个正确计划测试夹具、5个错误夹具均按预期通过/拒绝。没有真实模型周期标注结果。\n\n'
        '归档错误提案在小批原生回放中拒绝，归档成功提案通过；它们不是本轮新生成。完整历史门控和独立测试仍是接受新版本的后续条件。\n\n'
        f"本轮模型调用0；原生编译{cost['total']['native_compile_calls']}、执行{cost['total']['native_execute_calls']}（含编译冒烟）。\n\n"
        '真实执行需新增最多2次授权：先1次周期标注；仅标注通过才再调用1次生成SVA。前一阶段授权已全部使用。\n',encoding='utf-8')
    print('PREPARED',dict(windows=len(windows),model_calls=0),flush=True)


def run(prep,out,authorization):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==2 and auth['endpoint']==protocol['endpoint']
    assert auth['run_output']==out.relative_to(loop.ROOT).as_posix()
    for n,h in read(prep/'prepared_hashes.json').items():assert digest(prep/n)==h,n
    for n,h in protocol['source_hashes'].items():assert digest(loop.ROOT/'scripts'/n)==h,n
    loop.prepare(out);snapshot(out);shutil.copy2(authorization,out/'authorization.json')
    dump(out/'protocol.json',protocol);models=[]
    initial=read(prep/'shared_initial.json');current=initial;status='not_started'
    try:
        model=PlanModel(out/'plan',read(prep/'model_config.json'),read(prep/'plan_request.preview.json'));models.append(model)
        call,plan=model.call(out/'plan/model_call',initial,'stall_stability',{},'applicability_labeling')
        decision=validate_plan(plan,read(prep/'applicability.expected.private.json'))
        dump(out/'plan/decision.json',decision)
        if not decision['accepted']:
            status='applicability_rejected_no_sva_generation';return
        binding=read(PREP/'s3203/baseline_binding.json');before=read(portable(binding['result_path']))
        assert digest(portable(binding['result_path']))==binding['result_sha256']
        model=VerifiedPlanModel(out/'sva',read(prep/'model_config.json'),plan);models.append(model)
        call,candidate=model.call(out/'sva/model_call',initial,'stall_stability',initial_feedback(before),'core_fresh_boundary_repair')
        if candidate is None:
            status='sva_generation_or_duplicate_rejected';return
        edit=read(out/'sva/model_call/model_edit.json')
        if edit['operation']!='replace_one':
            status='unexpected_edit_operation_rejected';return
        small_binding=read(prep/'baseline_binding.json')
        assert digest(portable(small_binding['path']))==small_binding['sha256']
        with extension.installed():
            small=loop.replay(candidate,out/'core/target_native',read(prep/'target_cases.json'))
            decision=native_target_gate(read(portable(small_binding['path'])),small,edit['assertion_id'])
            dump(out/'core/target_gate.json',decision)
            if not decision['accepted']:
                status='native_target_gate_rejected_before_full_history';return
            full=loop.replay(candidate,out/'core/history_native',read(PREP/'s3203/cases.json'))
            verdict=gate.decide(before['group']['ledger'],full['group']['ledger'],sorted(loop.inspect(before['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False,reasons=[dict(kind='native_unavailable')])
            verdict['accepted']=verdict['accepted'] and full['healthy']
            dump(out/'core/decision.json',verdict)
            if not verdict['accepted']:
                status='full_history_rejected';return
            current=candidate;loop.freeze(out/'core',current,'accepted_before_fresh_tests')
            from research28_cases import cases as short_cases
            from research21_cases import independent_cases
            from research32_search import stimulus
            seed=secrets.randbelow(2**31);fresh=short_cases(seed,True)+independent_cases(seed)
            for depth in (4,8):
                for duration in (9,17,24):
                    for mode in extension.MODES:
                        n=seed+len(fresh)
                        fresh.append(dict(id=f'independent34:{n}:d{depth}:{duration}:{mode}',depth=depth,pipeline=2,mode=mode,rows=stimulus(n,duration),split='independent_test'))
            used={loop.sha(c['rows']) for c in read(PREP/'s3203/cases.json')}
            for old in (loop.ROOT/'deliverables/research32_real_20261021_r01/independent/split.json',OLD/'independent/split.json'):
                used.update(loop.sha(c['rows']) for c in read(old)['cases'])
            assert not used&{loop.sha(c['rows']) for c in fresh}
            dump(out/'independent/split.json',dict(seed=seed,cases=fresh,frozen_hash=loop.sha(current),usage='no_feedback_no_selection'))
            result=loop.replay(current,out/'independent/native',fresh)
            for row in result.get('group',{}).get('ledger',[]):row['split']='independent_test'
            dump(out/'independent/native/result.json',result)
            status='accepted_and_fresh_replay_completed'
    except BaseException:
        status='execution_exception';raise
    finally:
        if not (out/'core/freeze.json').exists():loop.freeze(out/'core',current,'retained_after_gated_trial')
        calls=[c for m in models for c in m.calls]
        dump(out/'model_cost.json',dict(calls=len(calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls)))
        dump(out/'outcome.json',dict(status=status,model_calls=len(calls),accepted=loop.sha(current)!=loop.sha(initial),frozen_hash=loop.sha(current)))
        print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    if a.action=='prepare':prepare(out)
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
