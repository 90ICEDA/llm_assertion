"""Read-only audit of real multi-iteration results and untouched fresh tests.

Checks raw response -> exact assembly -> native decision -> frozen identity.
No model or simulator calls and no candidate selection from holdout results.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import research17_loop as loop
import research17_report as inventory
import research31_gate as gate
from research31_gate import portable
from research28_report import raw_response
from research30_ablation_report import metrics
from research32_model import assemble

read,dump=loop.read,loop.dump


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(run,prep,out):
    outcome=read(run/'outcome.json')
    assert outcome['status']=='bounded_real_refinement_and_fresh_replay_completed'
    out.mkdir(parents=True,exist_ok=False)
    protocol=read(prep/'protocol.json');initial=read(prep/'shared_initial.json')
    frozen_hashes=read(run/'all_freeze.json');split=read(run/'independent/split.json')
    checks=[];records=[];examples=[];calls=[];gate_exposures=[]
    def check(name,value,**context):checks.append(dict(check=name,passed=bool(value),**context))
    old_paths=[
        loop.ROOT/'deliverables/research28_valid_closed_loop_20261020_r01/development_plan.json',
        loop.ROOT/'deliverables/research28_valid_closed_loop_20261020_r01/core_independent/split.json',
        loop.ROOT/'deliverables/research29_drain_independent_20261020_r01/split.json',
        loop.ROOT/'deliverables/research30_ablation_20261020_r01/independent/split.json',
    ]
    old_paths+=sorted((loop.ROOT/'deliverables/research31_multiseed_20261020_r01').glob('s*/independent/split.json'))
    exposed=set();exposure_sources=[]
    for path in old_paths:
        data=read(path);cases=data if isinstance(data,list) else data['cases']
        exposed.update(loop.sha(c['rows']) for c in cases)
        exposure_sources.append(dict(path=str(path),sha256=digest(path),cases=len(cases)))
    for parent,pattern in (
        (loop.ROOT/'deliverables/research30_search_compare_20261020_r01','queries/s*/*/q*/initial/correct_stimulus/stimulus.json'),
        (portable(protocol['source_search']),'core/search/s*/*/q*/initial/correct_stimulus/stimulus.json')):
        paths=sorted(parent.glob(pattern));check('prior_search_has48inputs',len(paths)==48,path=str(parent))
        for path in paths:
            exposed.add(loop.sha(read(path)))
            exposure_sources.append(dict(path=str(path),sha256=digest(path),cases=1))
    fresh={loop.sha(c['rows']) for c in split['cases']}
    check('fresh_input_no_published_overlap',not fresh&exposed)
    # The pre-existing independent generator deliberately applies five faults
    # to each fresh_random input. Those are different fault scenarios, not five
    # independent input schedules. Preserve this pairing and report both counts.
    scenario_keys={(c['depth'],c['pipeline'],c['mode'],loop.sha(c['rows'])) for c in split['cases']}
    input_groups={h:[c for c in split['cases'] if loop.sha(c['rows'])==h] for h in fresh}
    shared=[g for g in input_groups.values() if len(g)>1]
    check('fresh_fault_scenarios_unique',len(scenario_keys)==len(split['cases']))
    check('shared_inputs_only_declared_random_fault_sweep',all(
        len(g)==5 and {c['mode'] for c in g}=={'corrupt','duplicate_payload','drop','reset_residue','stall_glitch'} and
        all(c.get('family')=='fresh_random' for c in g) and len({(c['depth'],c['pipeline']) for c in g})==1 for g in shared))
    check('rtl_unchanged_since_preparation',digest(run/'axis_fifo.v')==digest(prep/'axis_fifo.v'))
    check('holdout_created_after_all_freeze',(run/'independent/split.json').stat().st_mtime >= (run/'all_freeze.json').stat().st_mtime)
    for seed in protocol['seeds']:
        source=prep/f's{seed}';folder=run/f's{seed}'
        binding=read(source/'baseline_binding.json')
        before=read(portable(binding['result_path']))
        check('baseline_content_bound',digest(portable(binding['result_path']))==binding['result_sha256'],seed=seed)
        selected=read(source/'cases.json')
        check('selected_input_bound',loop.sha(selected)==binding['cases_hash'] and loop.sha(initial)==binding['candidate_hash'],seed=seed)
        check('fresh_inputs_disjoint_from_seed_development',not fresh&{loop.sha(c['rows']) for c in selected},seed=seed)
        original=loop.inspect(before['group']['ledger']);history=read(folder/'core/history.json')
        current=initial;replayed=before;iterations=[];gate_index=0
        for h in history:
            number=h['iteration'];version=folder/'core'/f'v{number}';call=version/'model_call'
            request=read(call/'request.json');result=read(call/'result.json');decision=read(version/'decision.json')
            calls.append(dict(seed=seed,iteration=number,**result))
            check('no_transport_retry',result['retries']==0,seed=seed,iteration=number)
            check('same_model_configuration',request['model']==protocol['model'] and request['seed']==seed and request['temperature']==0 and request['max_tokens']==1024,seed=seed,iteration=number)
            check('model_call_before_holdout', (call/'result.json').stat().st_mtime <= (run/'all_freeze.json').stat().st_mtime,seed=seed,iteration=number)
            check('history_matches_decision',h['decision']==decision,seed=seed,iteration=number)
            if number==0:
                check('first_request_identical_to_preview',request==read(source/'preview/request.preview.json'),seed=seed)
            else:
                import json
                feedback=json.loads(request['messages'][1]['content'])['boundary_repair']
                prior=folder/'core'/f'v{number-1}'
                prior_edit=read(prior/'model_call/model_edit.json') if (prior/'model_call/model_edit.json').exists() else None
                check('rejection_feedback_is_actual',feedback['previous_rejected_proposal']==prior_edit and feedback['actual_rejection']==read(prior/'decision.json'),seed=seed,iteration=number)
            edit=read(call/'model_edit.json') if (call/'model_edit.json').exists() else None
            if edit is not None:check('raw_model_bytes_match_edit',raw_response(call,edit),seed=seed,iteration=number)
            candidate=read(call/'candidate.json') if (call/'candidate.json').exists() else None
            if candidate is not None:
                check('exact_model_operand_assembly',assemble(edit,current)==candidate,seed=seed,iteration=number)
                after=read(version/'native/result.json')
                if after.get('group'):
                    computed=gate.decide(replayed['group']['ledger'],after['group']['ledger'],h['target_keys'])
                    saved=read(version/'historical_gate_audit.json')
                    check('gate_recalculation_matches',computed['accepted']==saved['accepted'] and computed['reasons']==saved['reasons'],seed=seed,iteration=number)
                    check('acceptance_requires_native_health',decision['accepted']==bool(computed['accepted'] and after['healthy']),seed=seed,iteration=number)
                    paired=read(folder/'paired_gate'/f'{gate_index}.json');gate_index+=1
                    gate_exposures.append(dict(seed=seed,iteration=number,**paired))
                    if decision['accepted']:current=candidate;replayed=after
            else:
                check('interface_or_transport_failure_rejected',not decision['accepted'],seed=seed,iteration=number)
            iterations.append(dict(iteration=number,model_edit=edit,call=result,decision=decision,
                native_counts=h['after'],retained_candidate_sha256=loop.sha(current)))
        final=read(folder/'core/frozen_candidate.json')
        check('freeze_matches_accepted_state',final==current,seed=seed)
        check('freeze_hashes_match',loop.sha(final)==frozen_hashes[str(seed)]==split['hashes'][str(seed)]==read(folder/'core/freeze.json')['candidate_sha256'],seed=seed)
        check('stop_at_first_acceptance',not any(h['decision']['accepted'] for h in history[:-1]),seed=seed)
        check('seed_call_limit',1<=len(history)<=3,seed=seed)
        info=loop.inspect(replayed['group']['ledger'])
        independent=read(run/'independent'/str(seed)/'result.json');test=loop.inspect(independent['group']['ledger'])
        variants=('valid_withdraw_stalled','valid_withdraw_release','long_valid_withdraw_stalled','long_valid_withdraw_release')
        by_variant={v:{k:sum(test['rows'][x]['variant']==v and test['rows'][x]['obligation']=='stall_stability' for x in test[k])
            for k in ('detections','misses','unknown','false_positives','triggers')} for v in variants}
        original_history_ids={r['evidence_id'] for r in before['group']['ledger'] if not (r['scenario_id'].startswith('acquired30:') or r['scenario_id'].startswith('long32:'))}
        historical_detections=original['detections']&original_history_ids
        missing=sorted(historical_detections-info['detections'])
        changed=[dict(id=b['id'],before=a['property'],after=b['property']) for a,b in zip(initial['assertions'],final['assertions']) if a['property']!=b['property']]
        record=dict(seed=seed,iterations=iterations,frozen_hash=loop.sha(final),changed_properties=changed,
            repeated_model_edits=len([i for i in iterations if i['model_edit'] is not None])-len({loop.sha(i['model_edit']) for i in iterations if i['model_edit'] is not None}),
            repeated_predicate_edits=len([i for i in iterations if i['model_edit'] is not None])-len({loop.sha({k:v for k,v in i['model_edit'].items() if k!='reason'}) for i in iterations if i['model_edit'] is not None}),
            resolved=read(folder/'core/summary.json')['resolved'],development=metrics(replayed),
            historical_detections=len(historical_detections),lost_historical_detections=missing,
            new_historical_false_positives=sorted((info['false_positives']&original_history_ids)-original['false_positives']),
            independent=metrics(independent),independent_by_boundary=by_variant,
            boundary_test_passed=independent['healthy'] and not(test['false_positives'] or test['unknown']) and all(v['detections']>0 and not(v['misses'] or v['unknown'] or v['false_positives']) for v in by_variant.values()),
            whole_case_complete=False)
        records.append(record)
        for key in sorted(original['misses']):
            row=original['rows'][key];path=portable(row['source_directory'])/'replay.json'
            replay=read(path);cycle=row['cycle']
            examples.append(dict(seed=seed,mechanism=row['variant'],original_gap=row,final_evidence=info['rows'][key],
                original_miss_classification='triggered_but_insufficient_constraint' if any(a['trigger'] for a in row['native']['assertions']) else 'not_triggered',
                source=str(path),source_sha256=digest(path),
                sampled_boundary=[s for s in replay['reference_trace'] if cycle-1<=s['cycle']<=cycle],
                accepted_pending_transactions=[t for t in replay['oracle']['transactions'] if t['accept_cycle']<cycle and
                    (t['response_cycle'] is None or t['response_cycle']>=cycle) and
                    (t['cancel_cycle'] is None or t['cancel_cycle']>cycle)],
                changed_properties=changed,iterations=iterations,historical_retained=len(historical_detections)-len(missing),
                historical_total=len(historical_detections),independent=by_variant[row['variant']],frozen_hash=loop.sha(final)))
    attempts=list(run.glob('s*/core/v*/model_call/attempt.json'))
    check('call_count_matches_physical_attempts',len(calls)==len(attempts)==outcome['model_calls']<=9)
    check('all_previews_precede_first_attempt',max((prep/n).stat().st_mtime for n in protocol['previews'])<=min(p.stat().st_mtime for p in attempts))
    for n,h in protocol['source_sha256'].items():
        check('executed_source_snapshot_bound',digest(run/'source_snapshot'/n)==h,source=n)
    files=inventory.artifacts(run);cost=inventory.cost_audit(run,files)
    dump(out/'cost.json',cost)
    manifest={p.relative_to(run).as_posix():digest(p) for p in files}
    dump(out/'manifest.json',manifest)
    verify=[n for n,h in manifest.items() if digest(run/n)!=h]
    check('artifact_manifest_verified',not verify)
    dump(out/'verification.json',dict(files=len(manifest),failures=verify,passed=not verify))
    summary=dict(seeds=len(records),development_resolved=sum(r['resolved'] for r in records),
        repeated_model_edits=sum(r['repeated_model_edits'] for r in records),
        repeated_predicate_edits=sum(r['repeated_predicate_edits'] for r in records),
        independent_boundary_passed=sum(r['boundary_test_passed'] for r in records),
        current_only_accepts_full_gate_rejects=sum(g['current_only_accepts'] and not g['full_gate_accepts'] for g in gate_exposures),
        applicable_gate_admission_corrections=sum(g['full_gate_accepts'] and not g['gate']['strict_gate_accepted'] for g in gate_exposures),
        reset_cancelled_trigger_exemptions=sum(len(g['gate']['exempt_nonapplicable_trigger_losses']) for g in gate_exposures),
        source='Real new model proposals only; archived gate example accounted separately.',
        model_calls=len(calls),authorized_maximum=9,unused_allowance=9-len(calls),
        fresh_fault_scenarios=len(split['cases']),fresh_distinct_input_schedules=len(fresh),
        shared_input_fault_groups=[[c['id'] for c in g] for g in shared],independent_seed=split['seed'],
        stability_scope='Three seeds, one artificial FIFO repair task; no broad stability or whole-parent/global claim.')
    result=dict(summary=summary,records=records,checks=checks,passed=all(c['passed'] for c in checks),
        paired_gates=gate_exposures,prior_exposed_inputs=exposure_sources,cost=cost['total'],
        protocol_stage_note='run/protocol.json preserves the preparation protocol verbatim, including its no_new_model_calls preparation-stage field. Actual calls are counted from attempt/result/stream records, not that copied flag.',
        audit_revision='r01 incorrectly required different input rows for every fault scenario. r02 counts distinct inputs and parameter/fault scenarios separately, and validates the original five-mode shared random sweep. No candidate, input, simulator result, or acceptance decision changed; r01 failed audit is retained.')
    dump(out/'results.json',result);dump(out/'case_examples.json',examples)
    shutil.copy2(__file__,out/'audit_source.py')
    lines=['# research32：真实多轮细化与冻结后验收','',
        f"新增授权上限 9 次，实际调用 {len(calls)} 次，达到验收即停止，无传输重试。三个种子全部冻结后才生成同一批 {len(fresh)} 条不同输入，组成 {len(split['cases'])} 个参数/故障场景，独立种子 {split['seed']}。两个 fresh_random 输入分别用于五种故障，不计为十条不同输入。",'',
        '| 种子 | 实际调用 | 开发漏报（前→后） | 历史检出保持 | 独立检出/漏报 | 独立误报/当前 unknown | 后续归因 unknown |',
        '|---|---:|---|---|---|---|---:|']
    for r in records:
        t=r['independent']['counts'];d=r['development']['counts']
        lines.append(f"| {r['seed']} | {len(r['iterations'])} | 4 → {d['misses']} | {r['historical_detections']-len(r['lost_historical_detections'])}/{r['historical_detections']} | {t['detections']}/{t['misses']} | {t['false_positives']}/{t['unknown']} | {t['later_attribution_unknown']} |")
    lines+=['',f"开发验收 {summary['development_resolved']}/3；短/长背压保持与解除四类边界的新独立验收 {summary['independent_boundary_passed']}/3。计数为义务采样记录，不能当作独立 Bug 数；同一独立批次在三份冻结集合上的结果不能合并当作三倍独立样本。",'',
        '初版审计把共享随机输入误判为重复场景，失败告警保留在 research32_real_report_20261021_r01。修正版仅更正分母和场景身份检查；没有修改断言、测试输入或原生结果，也没有重新调用模型。','',
        '## 真实修改轨迹','']
    for r in records:
        lines.append(f"种子 {r['seed']}，冻结哈希 `{r['frozen_hash']}`：")
        for change in r['changed_properties']:
            lines.append(f"- {change['id']}：`{change['before']}` → `{change['after']}`。")
        for iteration in r['iterations']:
            lines.append(f"- 第 {iteration['iteration']+1} 次：{iteration['call']['candidate_status']}；接受={iteration['decision']['accepted']}；拒绝原因={[x['kind'] for x in iteration['decision']['reasons']]}。")
        lines.append('')
    lines+=['原始独立事务证据、接受周期、边界采样、精确模型编辑、历史回放与对应独立测试计数见 case_examples.json。', '',
        f"本次自然提案中，“当前检查接受但完整门控拒绝”共 {summary['current_only_accepts_full_gate_rejects']} 次；种子内完全重复的模型编辑共 {summary['repeated_model_edits']} 次，仍计入真实成本。复位取消适用性规则纠正旧严格门控的接受结果 {summary['applicable_gate_admission_corrections']} 次，累计豁免 {summary['reset_cancelled_trigger_exemptions']} 条非适用触发。与前一阶段回顾性归档门控案例分开报告；不把未发生的退化拒绝算作机制收益。",'',
        '## 成本与验证范围','',f"实际成本：`{cost['total']}`。金额不可用。准备/搜索/归档控制成本另见 research32_report_20261021_r01，旧公共历史成本没有重复算作本轮新执行。",'',
        f"完整性与隔离检查 {sum(c['passed'] for c in checks)}/{len(checks)}；{len(manifest)} 个运行文件哈希复核。首轮请求与预览一致，后续请求仅取开发诊断，最终候选来自真实原始响应的精确拼装。",'',
        '独立测试逐义务分母和未曝光场景见 results.json。未发现违例不是形式化证明，历史保护保持仅限回放证据，后续归因 unknown 未排除。真实历史父 Bug、全五义务完整案例通过和更广泛模型稳定性不能由本批结果推出。研究28项目冻结版本未替换。', '',
        '本批 drain_no_loss 没有目标违例曝光，冻结集合的该义务触发也为 0，不能将 0 漏报解释为排空通过；research29 的排空验收仅保留其原冻结集合和原证据范围。','',
        '实际命令（输出目录须不存在；该命令会消耗授权调用，不能作为只读报告命令重复运行）：','```powershell',
        'wsl -- python3 scripts/research32_campaign.py run --prepared deliverables/research32_prepare_20261021_r01 --out deliverables/research32_real_20261021_r01 --authorization deliverables/research32_prepare_20261021_r01/authorization.json','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert result['passed'],[c for c in checks if not c['passed']]
    print(dict(summary=summary,cost=cost['total'],checks=len(checks),verified_files=len(manifest)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('run','prepared','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();main(a.run.resolve(),a.prepared.resolve(),a.out.resolve())
