"""Read-only audit of prepared contrast feedback and optional genuine retries."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import research17_loop as loop
from research17_report import artifacts, cost_audit
from research33_model import fingerprint, tokens, screen
from research32_model import assemble
from research28_report import raw_response, portable
from research30_ablation_report import metrics
import research31_gate as gate


def audit_real(prep, run, out, check):
    read=loop.read
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    outcome=read(run/'outcome.json')
    check('real_trial_finished',outcome['status']=='real_contrast_retries_completed')
    protocol=read(prep/'protocol.json');initial=read(prep/'shared_initial.json')
    split=read(run/'independent/split.json');freezes=read(run/'all_freeze.json')
    fresh={loop.sha(c['rows']) for c in split['cases']}
    scenario_keys={(c['depth'],c['pipeline'],c['mode'],loop.sha(c['rows'])) for c in split['cases']}
    check('distinct_parameter_fault_scenarios',len(scenario_keys)==len(split['cases']))
    check('holdout_created_after_freeze',(run/'independent/split.json').stat().st_mtime >= (run/'all_freeze.json').stat().st_mtime)
    check('rtl_identical_to_prepared',digest(run/'axis_fifo.v')==digest(prep/'axis_fifo.v'))
    # Reuse the prior published exposure inventory, not its outcome as a test.
    published=read(loop.ROOT/'deliverables/research32_real_report_20261021_r02/results.json')
    exposure_paths=[portable(x['path']) for x in published['prior_exposed_inputs']]
    exposure_paths.append(loop.ROOT/'deliverables/research32_real_20261021_r01/independent/split.json')
    exposed=set()
    for path in exposure_paths:
        data=read(path)
        if path.name=='stimulus.json':exposed.add(loop.sha(data))
        else:
            cases=data if isinstance(data,list) else data['cases']
            exposed.update(loop.sha(c['rows']) for c in cases)
    check('fresh_inputs_disjoint_from_published_inputs',not fresh&exposed)
    records=[];examples=[]
    for seed in protocol['seeds']:
        prefix=f's{seed}:';source=prep/f's{seed}';folder=run/f's{seed}'
        binding=read(source/'baseline_binding.json');before=read(portable(binding['result_path']))
        check(prefix+'baseline_bound',digest(portable(binding['result_path']))==binding['result_sha256'])
        selected=read(source/'cases.json')
        check(prefix+'cases_and_candidate_bound',loop.sha(selected)==binding['cases_hash'] and loop.sha(initial)==binding['candidate_hash'])
        check(prefix+'fresh_inputs_disjoint_from_development',not fresh&{loop.sha(c['rows']) for c in selected})
        history=read(folder/'core/history.json');check(prefix+'one_call',len(history)==1)
        h=history[0];version=folder/'core/v0';call=version/'model_call'
        request=read(call/'request.json');result=read(call/'result.json');decision=read(version/'decision.json')
        check(prefix+'exact_prepared_request',request==read(source/'preview/request.preview.json'))
        check(prefix+'no_transport_retry',result['retries']==0)
        check(prefix+'history_matches_decision',h['decision']==decision)
        check(prefix+'call_before_freeze',(call/'result.json').stat().st_mtime <= (run/'all_freeze.json').stat().st_mtime)
        edit=read(call/'model_edit.json') if (call/'model_edit.json').exists() else None
        candidate=read(call/'candidate.json') if (call/'candidate.json').exists() else None
        if edit is not None:check(prefix+'raw_response_matches_edit',raw_response(call,edit))
        current=initial;replayed=before;after=None;screening=None
        if candidate is not None:
            check(prefix+'exact_assembly_of_model_operands',assemble(edit,initial)==candidate)
            screening=read(call/'proposal_screen.json')
            check(prefix+'screen_recalculation',screen(candidate,initial,{'current_gap_ids':h['target_keys']})==screening)
            if not screening['accepted_for_native']:
                check(prefix+'duplicate_not_executed',not (version/'native').exists())
                check(prefix+'duplicate_classified_and_rejected',not decision['accepted'] and decision['reasons']==[screening])
            else:
                after=read(version/'native/result.json')
                if after.get('group'):
                    computed=gate.decide(before['group']['ledger'],after['group']['ledger'],h['target_keys'])
                    saved=read(version/'historical_gate_audit.json')
                    check(prefix+'gate_recalculation',all(computed[k]==saved[k] for k in (
                        'accepted','reasons','gate_version','exempt_nonapplicable_trigger_losses','strict_gate_accepted')))
                    check(prefix+'healthy_native_acceptance_required',decision['accepted']==bool(computed['accepted'] and after['healthy']))
                    if decision['accepted']:current=candidate;replayed=after
        else:check(prefix+'unusable_model_output_rejected',not decision['accepted'])
        final=read(folder/'core/frozen_candidate.json')
        check(prefix+'accepted_or_rollback_freeze',final==current)
        check(prefix+'all_freeze_hashes_match',loop.sha(final)==freezes[str(seed)]==split['hashes'][str(seed)]==read(folder/'core/freeze.json')['candidate_sha256'])
        original=loop.inspect(before['group']['ledger']);info=loop.inspect(replayed['group']['ledger'])
        proposed_info=loop.inspect(after['group']['ledger']) if after and after.get('group') else None
        hist_ids={r['evidence_id'] for r in before['group']['ledger'] if not r['scenario_id'].startswith(('acquired30:','long32:'))}
        protected=original['detections']&hist_ids
        target_rows=[proposed_info['rows'].get(key) for key in h['target_keys']] if proposed_info else []
        target_rows=[r for r in target_rows if r]
        independent=read(run/'independent'/str(seed)/'result.json');test=loop.inspect(independent['group']['ledger'])
        variants=('valid_withdraw_stalled','valid_withdraw_release','long_valid_withdraw_stalled','long_valid_withdraw_release')
        boundaries={v:{k:sum(test['rows'][x]['variant']==v and test['rows'][x]['obligation']=='stall_stability' for x in test[k]) for k in ('detections','misses','unknown','false_positives','triggers')} for v in variants}
        changes=[dict(id=b['id'],before=a['property'],after=b['property']) for a,b in zip(initial['assertions'],final['assertions']) if a['property']!=b['property']]
        record=dict(seed=seed,edit=edit,call=result,screening=screening,decision=decision,
                    changed_properties=changes,frozen_hash=loop.sha(final),development=metrics(replayed),
                    rejected_proposal_metrics=metrics(after) if after and after.get('group') and not decision['accepted'] else None,
                    proposal_target_rows=len(target_rows),
                    proposal_target_rows_with_any_trigger=sum(any(a['trigger'] for a in r['native']['assertions']) for r in target_rows),
                    proposal_target_rows_with_causal_detection=sum(any(a['causal_detection'] for a in r['native']['assertions']) for r in target_rows),
                    historical_detections=len(protected),historical_retained=len(protected&info['detections']),
                    new_historical_false_positives=sorted((info['false_positives']&hist_ids)-original['false_positives']),
                    independent=metrics(independent),independent_by_boundary=boundaries,
                    boundary_test_passed=independent['healthy'] and not(test['false_positives'] or test['unknown']) and all(v['detections']>0 and not(v['misses'] or v['unknown'] or v['false_positives']) for v in boundaries.values()),whole_case_complete=False)
        records.append(record)
        cards=read(source/'contrasts.json')
        for key in sorted(original['misses']):
            row=original['rows'][key];path=portable(row['source_directory'])/'replay.json';replay=read(path);cycle=row['cycle']
            examples.append(dict(seed=seed,mechanism=row['variant'],initial_evidence=row,final_evidence=info['rows'][key],
                proposed_evidence=proposed_info['rows'].get(key) if proposed_info else None,
                actual_contrast=next((c for c in cards if c['evidence_id']==key),None),
                source=str(path),source_sha256=digest(path),
                accepted_pending_transactions=[t for t in replay['oracle']['transactions'] if t['accept_cycle']<cycle and (t['response_cycle'] is None or t['response_cycle']>=cycle) and (t['cancel_cycle'] is None or t['cancel_cycle']>cycle)],
                changed_properties=changes,edit=edit,decision=decision,historical_retained=record['historical_retained'],
                historical_total=len(protected),independent=boundaries[row['variant']],frozen_hash=loop.sha(final)))
    for n,h in protocol['source_hashes'].items():check('executed_source:'+n,digest(run/'source_snapshot'/n)==h)
    attempts=list(run.glob('s*/core/v*/model_call/attempt.json'))
    check('exact_two_attempts',len(attempts)==read(run/'model_cost.json')['calls']==2)
    files=artifacts(run);manifest={p.relative_to(run).as_posix():digest(p) for p in files}
    loop.dump(out/'run_manifest.json',manifest)
    check('run_manifest_verified',all(digest(run/n)==h for n,h in manifest.items()))
    summary=dict(records=records,accepted=sum(r['decision']['accepted'] for r in records),
                 independent_boundary_passed=sum(r['boundary_test_passed'] for r in records),
                 identical_edit_across_seeds=all(r['edit'] is not None for r in records) and len({loop.sha(r['edit']) for r in records})==1,
                 distinct_response_ids=len({r['call'].get('response_id') for r in records}),
                 fresh_input_schedules=len(fresh),fresh_parameter_fault_scenarios=len(split['cases']),
                 independent_seed=split['seed'],verified_files=len(manifest),
                 scope='Two selected prior failures; targeted follow-up, not unbiased stability or full-case validation.')
    loop.dump(out/'results.json',summary);loop.dump(out/'case_examples.json',examples)
    return summary


def audit(prep, out, run=None):
    out.mkdir(parents=True, exist_ok=False)
    checks=[]
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
    protocol=loop.read(prep/'protocol.json')
    qualification=loop.read(prep/'qualification.json')
    initial=loop.read(prep/'shared_initial.json')
    check('native_local_qualification', qualification['passed'])
    check('six_actual_archived_repeats_blocked',len(qualification['archived_repeats'])==6 and all(
        not r['decision']['accepted_for_native'] for r in qualification['archived_repeats']))
    check('four_missing_rows_repaired_by_archived_control',
          qualification['positive_control_before']['misses']==4 and qualification['positive_control_after']['misses']==0)
    check('metadata_is_not_a_new_property',fingerprint(dict(initial,reason='different wording'))==fingerprint(initial))
    changed=copy.deepcopy(initial)
    text=changed['assertions'][0]['property']
    changed['assertions'][0]['property']=text.replace('|=>','|->') if '|=>' in text else text.replace('|->','|=>')
    check('timing_change_requires_native_validation',fingerprint(changed)!=fingerprint(initial))
    check('separate_operators_not_conflated',tokens('mvalid && mready')!=tokens('mvalid & & mready'))
    check('outer_parentheses_and_spaces_only',tokens('((mvalid && mready))')==tokens('mvalid&&mready'))
    check('no_false_rejection_without_known_gap',screen(initial,initial,{})['accepted_for_native'])
    check('known_rejected_tokens_are_rejected',not screen(changed,initial,{},[fingerprint(changed)])['accepted_for_native'])
    check('novel_is_not_an_acceptance',screen(changed,initial,{})['kind']=='novel_candidate_requires_native_validation')
    success=loop.read(loop.ROOT/'deliverables/research32_real_20261021_r01/s3209/core/frozen_candidate.json')
    for relative, expected in protocol['previews'].items():
        path=prep/relative
        check(relative+':sealed',hashlib.sha256(path.read_bytes()).hexdigest()==expected)
        request=loop.read(path);body=json.loads(request['messages'][1]['content'])
        cards=body['counterexample_first']['contrasts']
        check(relative+':four_contrasts',len(cards)==4)
        check(relative+':independent_attribution',all(c['target_evidence']['attribution']=='confirmed' for c in cards))
        check(relative+':valid_difference_explicit',all('mvalid' in c['differing_sampled_signals'] for c in cards))
        compact=''.join(request['messages'][1]['content'].split())
        newly_successful=success['assertions'][2]['property']
        check(relative+':successful_edit_not_supplied',''.join(newly_successful.split()) not in compact)
    for name,expected in protocol['source_hashes'].items():
        check('source_snapshot:'+name,hashlib.sha256((prep/'source_snapshot'/name).read_bytes()).hexdigest()==expected)
    costs={'local':cost_audit(prep,artifacts(prep))}
    result=dict(checks=checks,qualification=qualification,protocol=protocol,real_run=None,
                scope='Archived controls demonstrate local behavior only. Fresh model effectiveness requires actual remote results.')
    if run:
        result['real_run']=loop.read(run/'outcome.json')
        costs['real']=cost_audit(run,artifacts(run))
        result['real_audit']=audit_real(prep,run,out,check)
        check('model_cost_crosscheck',all(costs['real']['recorded_model_cost_crosscheck'].values()))
    result['all_checks_passed']=all(c['passed'] for c in checks)
    loop.dump(out/'verification.json',result)
    loop.dump(out/'cost.json',costs)
    shutil.copy2(Path(__file__),out/'audit_source.py')
    rows=['# research33：针对重复无效提案的修正','',
          '旧实验中的反例确实到达模型；两个失败种子各三轮仍重复数据保持性质，遗漏 valid 撤销。不是接口未接通。','',
          '本轮改为先呈现四条逐周期正确/故障对照，突出相同与不同信号，移除旧性质文本以减少照抄。模型自行生成表达式；新表达式仍必须通过原生回放和防退化门控。',
          '增加性质词元及时间关系指纹；重复无效性质在原生执行前拒绝并留档。仅支持有限的语法同一性判断，不宣称语义等价判定。重复提案单独分类，不归为接口或原生工具失败。','',
          f"本地检查：{sum(c['passed'] for c in checks)}/{len(checks)}。6/6 历史重复提案可识别。归档成功版本的原生正对照：4→0 漏报、误报0，后续归因 unknown 140；这不是本轮模型生成成功。",
          f"本地成本：{costs['local']['total']['native_compile_calls']} 次编译、{costs['local']['total']['native_execute_calls']} 次执行（含编译冒烟）、模型调用0、形式化0。",'',
          '真实效果状态：'+('已运行，详见 verification.json 的 real_run 与 cost.json；保留所有失败。' if run else '尚待真实调用验证。原9次授权已用7次，剩余2次转用于新试验的授权待确认；未提交远程请求。'),'',
          '新试验针对两个历史失败种子，各一次；属于有针对性的后续实验，不是无偏多种子稳定性估计，也不是四组消融。所有终版冻结后才生成新测试；测试不反馈模型。', '',
          '复现本地准备（输出目录必须不存在）：','```powershell',
          'wsl -- python3 scripts/research33_campaign.py prepare --out deliverables/research33_prepare_new',
          '```','',
          '授权后真实运行入口：','```powershell',
          f'wsl -- python3 scripts/research33_campaign.py run --prepared {prep.relative_to(loop.ROOT).as_posix()} --out deliverables/research33_real_20261021_r01 --authorization {prep.relative_to(loop.ROOT).as_posix()}/authorization.json',
          '```','',
          '此处仿真通过只适用于记录的证据，不能代替形式化证明；局部防退化不能推及全部输入。']
    if run:
        real=result['real_audit'];cost=costs['real']['total']
        rows+=['','| 种子 | 修改接受 | 开发漏报 | 历史检出保持 | 独立检出/漏报 | 误报/当前unknown | 后续归因unknown |',
               '|---|---|---:|---|---|---|---:|']
        for r in real['records']:
            counts=r['independent']['counts'];dev=r['development']['counts']
            rows.append(f"| {r['seed']} | {r['decision']['accepted']} | 4→{dev['misses']} | {r['historical_retained']}/{r['historical_detections']} | {counts['detections']}/{counts['misses']} | {counts['false_positives']}/{counts['unknown']} | {counts['later_attribution_unknown']} |")
        rows+=['','上述检出、漏报和 unknown 按义务×采样周期证据行计数，不能当作独立故障数量。被拒绝版本的退化没有进入冻结版本。']
        for r in real['records']:
            rows+=['',f"种子 {r['seed']} 的提案在 {r['proposal_target_rows']} 条当前目标证据中，有效触发 {r['proposal_target_rows_with_any_trigger']} 条、因果检出 {r['proposal_target_rows_with_causal_detection']} 条。拒绝原因："+
                   '；'.join(f"{d['kind']} ({len(d.get('evidence_keys',[]))} 证据行)" for d in r['decision']['reasons'])]
            if r['edit']:
                rows+=['```json',json.dumps(r['edit'],ensure_ascii=False,indent=2),'```']
        rows+=['',f"真实接受 {real['accepted']}/2，独立边界验收 {real['independent_boundary_passed']}/2。新测试种子 {real['independent_seed']}，{real['fresh_input_schedules']} 条不同输入、{real['fresh_parameter_fault_scenarios']} 个参数/故障场景。",
               f"两个请求是否产生完全相同的修改：{real['identical_edit_across_seeds']}；服务返回的不同 response_id 数：{real['distinct_response_ids']}。提交 seed 参数不代表已验证服务端使用了该参数。",
               f"本轮真实调用 {cost['model_calls']}，输入/输出 tokens {cost['prompt_tokens_total']}/{cost['completion_tokens_total']}，原生编译 {cost['native_compile_calls']}、执行 {cost['native_execute_calls']}（含冒烟 {cost['compile_smoke_execute_calls']}），形式化0，金额不可用。",'',
               '实际修改、原始响应校验、接受/拒绝原因见 results.json；逐条反例、已接受事务和独立边界结果见 case_examples.json。排空等未曝光义务不能按通过处理；whole_case_complete 保持 false。']
    (out/'SUMMARY.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    loop.dump(out/'manifest.json',{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(passed=result['all_checks_passed'],checks=len(checks),costs={k:v['total'] for k,v in costs.items()})))
    assert result['all_checks_passed'],'audit_failed'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--run',type=Path)
    a=p.parse_args();audit(a.prepared.resolve(),a.out.resolve(),a.run.resolve() if a.run else None)
