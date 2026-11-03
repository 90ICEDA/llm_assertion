"""Read-only audit of research136's stopped real pilot; no model or native run."""
import argparse
import json
from pathlib import Path
import research136_prospective_history as p


def audit(prep, run, out):
    opened = p.q.guard()
    p.verify(prep)
    out.mkdir(parents=True, exist_ok=False)
    checks = []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    original = {p.rel(f): p.digest(f) for f in run.rglob('*') if f.is_file()}
    call_dir = run/'shared/v0/model_call'
    result = p.read(call_dir/'result.json')
    outcome = p.read(run/'outcome.json')
    grant = p.read(run/'authorization.json')
    request = p.read(call_dir/'request.json')
    edit = p.read(call_dir/'model_edit.json')
    assembled = p.read(call_dir/'response.assembled.json')
    check('grant_purpose', grant['purpose'] == p.PURPOSE)
    check('grant_calls', grant['authorized_calls'] == 2)
    check('grant_bound_to_seal', grant['prepared_sha256'] == p.digest(prep/'sealed.json'))
    check('grant_bound_to_run', grant['run_output'] == p.rel(run))
    check('endpoint_model', grant['endpoint'] == result['endpoint'] == p.transport.DEFAULT_URL
          and grant['model'] == result['model'] == result['actual_server_model'] == p.s.MODEL)
    check('exact_sealed_request', request == p.read(prep/'request.preview.json'))
    check('same_shared_request', request == p.read(prep/'arms/O/request.preview.json')
          == p.read(prep/'arms/H/request.preview.json'))
    check('response_not_hand_repaired', json.loads(assembled['message']['content']) == edit)
    check('service_completed', result['status'] == 'response_received'
          and result['stream_terminal_received'] and result['retries'] == 0)
    check('interface_error_recorded', result['candidate_status'] == 'interface_rejected'
          and result['candidate_error']['detail'] == 'op_slot_labels')
    body = json.loads(request['messages'][1]['content'])
    check('slot_constraint_explicit', 'First item labels illegal_branch_persists; remaining items label op_bit28_illegal.' in body['output_contract'])
    check('second_branch_slot', edit['assertions'][1]['obligations'] == ['illegal_branch_persists'])
    # Reproduce only the syntax/interface decision; do not change labels,
    # merge properties or execute this noncompliant proposal retrospectively.
    try:
        p.q.adapt(edit, p.read(prep/'initial.json'))
    except ValueError as exc:
        check('same_adapter_rejection', str(exc) == 'op_slot_labels')
    else:
        raise AssertionError('adapter unexpectedly accepted')
    check('no_executable_candidate', not (call_dir/'candidate.json').exists())
    check('no_repeat_misclassification', not (run/'shared/v0/repeat_rejection.json').exists())
    check('one_physical_attempt', len(list(run.rglob('attempt.json'))) == 1
          and len(p.read(run/'budget_ledger.json')) == outcome['actual_model_calls'] == 1)
    check('no_recovery_dispatch', not (run/'history').exists())
    check('no_native_dispatch', not list(run.rglob('compile.json')) and not list(run.rglob('execute.json')))
    check('correct_branch', outcome['completed'] and outcome['status'] == 'stop_interface_or_repeat'
          and outcome['first'] == dict(O=False, H=False, branch='stop_interface_or_repeat', measured=False))
    check('not_recovery_failure_rate', not outcome['recovery_rate_estimable'])
    check('no_acceptance_or_independent', not outcome['recovered_full151']
          and outcome['independent'] is None and not outcome['qualified_chain']
          and not (run/'terminal_freeze.json').exists() and not (run/'independent_cases.json').exists())
    initial = p.read(prep/'initial.json')
    for arm in ('O', 'H'):
        folder = run/'arms'/arm/'v0'
        transition = p.read(folder/'transition.json')
        check(arm+'_retained_exact_baseline', p.read(folder/'active.json') == p.read(folder/'before.json') == initial)
        check(arm+'_durable_rejection', not transition['accepted'] and transition['proposal_sha256'] is None
              and transition['previous_sha256'] == transition['active_sha256'] == p.x.old.acceptance.sha(initial))
    cost = p.read(run/'cost.json')['total']
    check('usage_crosscheck', cost['prompt_tokens_total'] == result['prompt_tokens'] == assembled['service_done']['usage']['prompt_tokens']
          and cost['completion_tokens_total'] == result['completion_tokens'] == assembled['service_done']['usage']['completion_tokens'])
    check('zero_native_formal_cost', all(cost[k] == 0 for k in ('native_compile_calls', 'native_execute_calls', 'compile_smoke_execute_calls', 'formal_calls')))
    check('budget_reservation_exact', p.read(run/'budget_ledger.json')[0]['request_sha256'] == p.x.old.acceptance.sha(request))
    check('original_run_unchanged', original == {p.rel(f): p.digest(f) for f in run.rglob('*') if f.is_file()})
    p.verify(prep)
    baseline = p.read(p.QUAL/'fixture_results.private.json')['baseline']
    check('retained_prior_partial_protection', baseline['retained_detections'] == 270)
    report = dict(passed=True, checks=len(checks), real_calls=1, authorized_maximum=2,
                  remaining_call_condition_not_met=True, new_accepted_versions=0,
                  full151_replays=0, new_independent_tests=0, native_rule_comparison_measured=False,
                  additional_historical_rejections=0, recovery_attempts=0, recovery_rate=None,
                  retained_prior_baseline_detections=270, baseline_replayed_this_run=False,
                  failure_stage='interface_obligation_slot_binding', property_correctness='not_measured',
                  research133_read=False, tokens=dict(input=result['prompt_tokens'], output=result['completion_tokens']),
                  native_compiles=0, native_executions=0, formal_calls=0)
    p.dump(out/'audit.json', report)
    p.dump(out/'checks.json', checks)
    p.dump(out/'read_audit.json', sorted(opened))
    p.dump(out/'source_bindings.json', {**original, p.rel(Path(__file__)):p.digest(Path(__file__)),
                                      p.rel(prep/'sealed.json'):p.digest(prep/'sealed.json')})
    (out/'SUMMARY.md').write_text(f'''# research136：真实先导因接口不合规停止

实际调用1/最多2次，DeepSeek服务正常返回。模型提出4条性质，将BRANCH、OP各拆为首周期和保持周期。
请求明确要求第一条属于BRANCH，其余属于OP；第二条BRANCH违反封存槽位约束，原接口复核同样报op_slot_labels。
这是请求接口不合规，不是原生语法编译错误、工具不支持，也尚不能判定性质功能正确或错误。
原响应、流记录和模型理由完整保存，没有合并性质、改标签、替换位号或追改为接受。

|里程碑|实际结果|
|---|---|
|新真实模型响应|1|
|新接受版本|0|
|完整151事务回放|未启动|
|新独立验收|未启动|
|普通接受/历史额外拒绝|未形成可测量提案；实际额外拒绝0|
|自动恢复|条件未成立，调用0；恢复率不可估计|

O/H记录的false代表接口失败后的未接受状态，不能当作两个原生规则都独立拒绝。H没有产生额外拒绝。
两组active均保留原始基线哈希，其已有270个BRANCH检出为先前开发验证结果；本轮没有重新回放，也不能当作完整保护。
没有普通接受、历史拒绝且确认退化的机会，控制器依协议停止。未用1次额度只可用于原条件性恢复，不能作为新的格式重试或扩种子额度。

成本：模型输入{result['prompt_tokens']}、输出{result['completion_tokens']} tokens，服务耗时{result['wall_seconds']:.3f}秒；原生编译0、仿真0、形式化0；货币费用不可用。
本地审计{len(checks)}项通过，封存哈希和原执行产物未改变。research133独立数据未读取；本轮没有搜索机制比较，不改变既有搜索负结果。

下一步只需先本地审计义务映射对多条同义务性质的支持与位置假设，确定这种表达限制是否必要。
若改接口，应另立协议、重新验证同标准下的正负对照并封存，不能把本轮响应转换后计为本轮前瞻成功；不默认追加模型调用。

只读复核（输出目录必须是新目录；无模型/原生调用）：
```powershell
wsl -- python3 scripts/research138_pilot_result_audit.py --prepared {p.rel(prep)} --run {p.rel(run)} --out deliverables/research138_recheck
```
''', encoding='utf-8')
    p.dump(out/'sealed.json', {f.relative_to(out).as_posix():p.digest(f) for f in out.rglob('*') if f.is_file()})
    print('AUDIT138', len(checks), 'passed; real calls1, native0, accepted0; stopped as sealed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('prepared', 'run', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    audit(args.prepared.resolve(), args.run.resolve(), args.out.resolve())
