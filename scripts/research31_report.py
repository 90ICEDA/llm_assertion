"""Read-only gate validation/preparation and optional three-seed real-run audit."""
import argparse
import hashlib
from pathlib import Path
import shutil

import research17_loop as loop
import research17_report as audit
import research30_ablation as trial
import research31_gate as gate
from research30_ablation_report import portable, metrics
from research28_report import raw_response
from research15_evidence import merge_ledgers

read,dump=loop.read,loop.dump


def artifact_audit(folder,out):
    files=audit.artifacts(folder)
    cost=audit.cost_audit(folder,files)
    dump(out/'cost.json',cost)
    manifest={p.relative_to(folder).as_posix():audit.digest(p) for p in files}
    dump(out/'manifest.json',manifest)
    bad=[n for n,h in manifest.items() if audit.digest(folder/n)!=h]
    dump(out/'verification.json',dict(passed=not bad,files=len(files),failures=bad))
    return cost['total']


def experiment(run,prep,out):
    assert read(run/'outcome.json')['status']=='three_seed_four_arm_runs_completed'
    protocol=read(prep/'protocol.json');records=[];checks=[]
    examples=[]
    prior_paths=[
        loop.ROOT/'deliverables/research28_valid_closed_loop_20261020_r01/development_plan.json',
        loop.ROOT/'deliverables/research28_valid_closed_loop_20261020_r01/core_independent/split.json',
        loop.ROOT/'deliverables/research29_drain_independent_20261020_r01/split.json',
        loop.ROOT/'deliverables/research30_ablation_20261020_r01/independent/split.json']
    exposed=set()
    for path in prior_paths:
        value=read(path)
        exposed.update(loop.sha(c['rows']) for c in (value if isinstance(value,list) else value['cases']))
    search_inputs=sorted((loop.ROOT/'deliverables/research30_search_compare_20261020_r01/queries').glob(
        's*/*/q*/initial/correct_stimulus/stimulus.json'))
    assert len(search_inputs)==48,'source_search_inputs_incomplete'
    exposed.update(loop.sha(read(path)) for path in search_inputs)
    fresh_sets={}
    for seed in protocol['seeds']:
        folder=run/f's{seed}';prepared=prep/f's{seed}'
        assert read(folder/'outcome.json')['status']=='four_real_model_arms_completed'
        split=read(folder/'independent/split.json');initial=read(folder/'shared_initial.json')
        original=loop.inspect(read(prepared/'core/history/result.json')['group']['ledger'])
        baseline_groups=[read(prepared/'core/history/result.json')['group'],
                         read(prepared/'core/acquired/result.json')['group']]
        combined=merge_ledgers(baseline_groups)['ledger']
        baseline_info=loop.inspect(combined)
        dev=read(prepared/'history_cases.json')+read(prepared/'acquired_cases.json')
        fresh_sets[seed]={loop.sha(c['rows']) for c in split['cases']}
        checks.append(dict(seed=seed,check='fresh_input_no_overlap',
            passed=not ((exposed|{loop.sha(c['rows']) for c in dev})&fresh_sets[seed])))
        requests={}
        for name in trial.ARMS:
            arm=folder/'arms'/name;call=arm/'model_call'
            request=read(call/'request.json');requests[name]=request
            preview=read(prepared/'preview'/name/'request.preview.json')
            final=read(arm/'frozen_candidate.json');decision=read(arm/'decision.json')
            edit=read(call/'model_edit.json') if (call/'model_edit.json').exists() else None
            assembled=trial.Model.edit(edit,initial) if (call/'candidate.json').exists() else None
            checks.extend([
                dict(seed=seed,arm=name,check='precommitted_request',passed=request==preview),
                dict(seed=seed,arm=name,check='raw_model_preserved',passed=raw_response(call,edit) if edit else True),
                dict(seed=seed,arm=name,check='final_matches_decision',
                     passed=final==(assembled if decision['accepted'] else initial)),
                dict(seed=seed,arm=name,check='freeze_bound',
                     passed=loop.sha(final)==read(arm/'freeze.json')['candidate_sha256']==split['hashes'][name]),
                dict(seed=seed,arm=name,check='test_after_all_seed_arms_freeze',
                     passed=(folder/'independent/split.json').stat().st_mtime >= (folder/'all_arms_freeze.json').stat().st_mtime)])
            history=read(folder/'historical_audit'/name/'result.json')
            hist=loop.inspect(history['group']['ledger'])
            independent=read(folder/'independent'/name/'result.json')
            independent_info=loop.inspect(independent['group']['ledger'])
            entry=dict(seed=seed,arm=name,decision=decision,call=read(call/'result.json'),
                edit=edit,final_hash=loop.sha(final),historical=metrics(history),
                final_properties=[dict(id=x['id'],property=x['property']) for x in final['assertions']],
                changed_properties=[dict(id=x['id'],before=old['property'],after=x['property'])
                    for old,x in zip(initial['assertions'],final['assertions']) if old['property']!=x['property']],
                historical_original_detections=len(original['detections']),
                lost_historical_detections=sorted(original['detections']-hist['detections']),
                lost_historical_triggers=sorted(original['triggers']-hist['triggers']),
                new_historical_false_positives=sorted((hist['false_positives']&original['rows'].keys())-original['false_positives']),
                independent=metrics(independent),
                whole_case_complete=False,
                whole_case_scope='Only exposed first-attributable targets; later attribution unknowns and unexposed obligations prevent a whole-case/global claim.',
                independent_valid_boundaries={variant:{metric:sum(
                    independent_info['rows'][k]['variant']==variant and
                    independent_info['rows'][k]['obligation']=='stall_stability'
                    for k in independent_info[metric])
                    for metric in ('detections','misses','false_positives','unknown','triggers')}
                    for variant in ('valid_withdraw_stalled','valid_withdraw_release')},
                independent_seed=split['seed'])
            # Recompute the same rule on actual frozen A/B native replays.
            # This is observational, not an additional model arm or a changed
            # acceptance decision, and cannot influence any model request.
            if name in ('A','B'):
                before=combined if name=='B' else baseline_groups[0]['ledger']
                allowed={r['evidence_id'] for r in before}
                replayed=[r for r in history['group']['ledger'] if r['evidence_id'] in allowed]
                targets=sorted(baseline_info['misses']) if name=='B' else []
                counterfactual=gate.decide(before,replayed,targets)
                dump(out/'counterfactual'/f's{seed}_{name}.json',counterfactual)
                entry['gate_on_actual_frozen_candidate']=dict(
                    accepted=counterfactual['accepted'],reasons=counterfactual['reasons'],
                    exemptions=counterfactual['exempt_nonapplicable_trigger_losses'],
                    scope='Read-only post-freeze common-development audit; no new model arm and no changed decision.')
            if (arm/'historical_gate.json').exists():
                recorded=read(arm/'historical_gate.json')
                recalculated=gate.decide(read(arm/'before/result.json')['group']['ledger'],
                    read(arm/'proposed/result.json')['group']['ledger'],decision['target_keys'])
                checks.append(dict(seed=seed,arm=name,check='actual_corrected_gate_matches',
                    passed=recorded['gate_version']==gate.VERSION and
                           recorded['accepted']==recalculated['accepted'] and
                           recorded['reasons']==recalculated['reasons']))
                entry['gate']=dict(accepted=recorded['accepted'],strict_gate_accepted=recorded['strict_gate_accepted'],
                    exemptions=recorded['exempt_nonapplicable_trigger_losses'],reasons=recorded['reasons'])
            for key in sorted(baseline_info['misses']):
                original_gap=baseline_info['rows'][key]
                source=portable(original_gap['source_directory'])/'replay.json'
                replay=read(source);cycle=original_gap['cycle']
                examples.append(dict(seed=seed,arm=name,mechanism=original_gap['variant'],
                    exposure='Model feedback' if trial.ARMS[name]['search'] else 'Post-freeze audit only; not supplied to this arm',
                    original_gap=original_gap,after_frozen=hist['rows'][key],
                    samples=[s for s in replay['reference_trace'] if cycle-1<=s['cycle']<=cycle],
                    accepted_pending_before_edge=[t for t in replay['oracle']['transactions']
                        if t['accept_cycle']<cycle and
                        (t['response_cycle'] is None or t['response_cycle']>=cycle) and
                        (t['cancel_cycle'] is None or t['cancel_cycle']>cycle)],
                    changed_properties=entry['changed_properties'],model_edit=edit,decision=decision,
                    historical_original_detections=entry['historical_original_detections'],
                    historical_lost_detections=entry['lost_historical_detections'],
                    independent=entry['independent_valid_boundaries'][original_gap['variant']],
                    frozen_hash=entry['final_hash'],source=str(source),source_sha256=audit.digest(source)))
            records.append(entry)
        checks.extend([dict(seed=seed,check='A_C_prompt_equal',passed=requests['A']==requests['C']),
                       dict(seed=seed,check='B_D_prompt_equal',passed=requests['B']==requests['D'])])
    costs=artifact_audit(run,out/'run_artifacts')
    detailed_cost=read(out/'run_artifacts/cost.json')
    for record in records:
        seed,name=record['seed'],record['arm']
        record['cost']=dict(
            model_calls=1,prompt_tokens=record['call'].get('prompt_tokens'),
            completion_tokens=record['call'].get('completion_tokens'),
            model_wall_seconds=record['call'].get('wall_seconds'),
            native_by_stage={stage:dict(
                compiles=sum(c['kind']=='compile' and c['path'].startswith(prefix)
                             for c in detailed_cost['native_commands']),
                executions=sum(c['kind']=='execute' and c['path'].startswith(prefix)
                               for c in detailed_cost['native_commands']))
                for stage,prefix in (('decision',f's{seed}/arms/{name}/'),
                    ('common_history',f's{seed}/historical_audit/{name}/'),
                    ('independent',f's{seed}/independent/{name}/'))})
    checks.append(dict(check='exactly12calls',passed=costs['model_calls']==12))
    all_preview_times=[(prep/p).stat().st_mtime for p in protocol['preview_hashes']]
    attempts=list(run.glob('s*/arms/*/model_call/attempt.json'))
    checks.append(dict(check='all_prompts_fixed_before_first_call',
        passed=bool(attempts) and max(all_preview_times)<=min(p.stat().st_mtime for p in attempts)))
    checks.append(dict(check='same_gate_source',
        passed=protocol['gate_source_sha256']==hashlib.sha256(Path(gate.__file__).read_bytes()).hexdigest()))
    checks.append(dict(check='fresh_batches_disjoint_between_seeds',
        passed=all(not (fresh_sets[left]&fresh_sets[right])
                   for left in fresh_sets for right in fresh_sets if left<right)))
    for seed in protocol['seeds']:
        hashes=read(run/f's{seed}/source_snapshot/hashes.json')
        checks.append(dict(seed=seed,check='source_snapshot_hashes',
            passed=all(hashlib.sha256((run/f's{seed}/source_snapshot'/n).read_bytes()).hexdigest()==h
                       for n,h in hashes.items())))
    summary={}
    for name in trial.ARMS:
        rows=[r for r in records if r['arm']==name]
        summary[name]=dict(seeds=len(rows),accepted=sum(r['decision']['accepted'] for r in rows),
            changed_sets=sum(bool(r['changed_properties']) for r in rows),
            acquired_gaps_fully_resolved=sum(r['historical']['healthy'] and
                all(r['historical']['counts'][k]==0 for k in ('misses','unknown','false_positives')) for r in rows),
            valid_boundaries_fully_detected=sum(r['independent']['healthy'] and
                all(r['independent']['counts'][k]==0 for k in ('false_positives','unknown')) and
                all(v['detections']>0 and all(v[k]==0 for k in ('misses','false_positives','unknown'))
                for v in r['independent_valid_boundaries'].values()) for r in rows),
            independent={k:sum(r['independent']['counts'][k] for r in rows)
                         for k in ('detections','misses','false_positives','unknown','later_attribution_unknown')},
            lost_historical_detections=sum(len(r['lost_historical_detections']) for r in rows),
            new_historical_false_positives=sum(len(r['new_historical_false_positives']) for r in rows),
            note='Sums across repetitions, not independent bug discoveries or statistical superiority. changed_sets counts textual property differences, not semantic improvement.')
    contrasts=[]
    for seed in protocol['seeds']:
        by={r['arm']:r for r in records if r['seed']==seed}
        for label,treatment,control in [('search_without_gate','B','A'),('search_with_gate','D','C'),
                                        ('gate_without_search','C','A'),('gate_with_search','D','B')]:
            contrasts.append(dict(seed=seed,comparison=label,treatment=treatment,control=control,
                independent_delta={k:by[treatment]['independent']['counts'][k]-by[control]['independent']['counts'][k]
                                   for k in ('detections','misses','false_positives','unknown')},
                same_generated_predicate=(by[treatment]['edit'] or {}).get('assertions')==
                                         (by[control]['edit'] or {}).get('assertions'),
                note='Within-seed common holdout. Single model response per arm; different proposals confound direct gate-effect attribution.'))
    result=dict(records=records,checks=checks,passed=all(c['passed'] for c in checks),
                summary=summary,cost=costs,paired_contrasts=contrasts,
                prior_exposed_input_sources=[dict(path=str(p),sha256=audit.digest(p)) for p in prior_paths],
                prior_search_input_sources=[dict(path=str(p),sha256=audit.digest(p)) for p in search_inputs],
                gate_admission_corrections=[dict(seed=r['seed'],arm=r['arm'],
                    exemptions=r['gate']['exemptions'],
                    historical_remaining_misses=r['historical']['counts']['misses'])
                    for r in records if r.get('gate',{}).get('accepted') and not r['gate']['strict_gate_accepted']],
                gated_native_proposals=sum('gate' in r for r in records),
                natural_historical_regression_rejections=[dict(seed=r['seed'],arm=r['arm'],reasons=[
                    reason for reason in r['gate']['reasons'] if reason['kind'] in
                    ('lost_target_detection','lost_obligation_trigger','new_legal_false_positive')])
                    for r in records if 'gate' in r and any(reason['kind'] in
                    ('lost_target_detection','lost_obligation_trigger','new_legal_false_positive')
                    for reason in r['gate']['reasons'])])
    dump(out/'multiseed_results.json',result)
    dump(out/'case_examples.json',examples)
    assert result['passed'],'audit_failed'
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--validation',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--run',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    out.mkdir(parents=True,exist_ok=True)
    validation=a.validation.resolve();prep=a.prepared.resolve()
    v=read(validation/'outcome.json');protocol=read(prep/'protocol.json')
    assert v['status']=='gate_validated_on_recorded_scope'
    previews={n:hashlib.sha256((prep/n).read_bytes()).hexdigest()==h for n,h in protocol['preview_hashes'].items()}
    assert all(previews.values())
    cost=dict(validation=artifact_audit(validation,out/'validation'),
              preparation=artifact_audit(prep,out/'preparation'))
    supplement=validation/'gate_boundary_negative_controls/required_legal_trigger.json'
    required=read(supplement)['decision'] if supplement.exists() else None
    result=dict(gate_version=gate.VERSION,validation=v,required_legal_trigger_negative_control=required,
        request_hash_checks=previews,remote_calls_this_stage=0,
        multiseed_status='prepared_not_executed_pending_new_12_call_authorization')
    if a.run:
        run_result=experiment(a.run.resolve(),prep,out)
        result['multiseed_status']='completed_three_seeds_four_arms'
        result['multiseed_summary']=run_result['summary'];cost['run']=run_result['cost']
        result['remote_calls_this_stage']=run_result['cost']['model_calls']
    dump(out/'results.json',result);dump(out/'cost.json',cost)
    lines=['# Research31：义务适用性门控修正与多种子消融','',
        '门控 v1 只豁免有双侧原生采样、独立 oracle 和同激励绑定支持的“前一拍复位取消背压义务”触发。'
        '其他触发丢失仍拒绝；无法判定不按通过处理。历史检出丢失、新误报、新缺口未修复、缺失回放和证据改变仍按原严格规则处理。','',
        '已执行五个开发场景、三套断言的原生回放。有效修复检出 13→15、漏报 2→0，门控接受；'
        '人为关闭前件的负对照重新漏报 2 条，因历史检出丢失及当前缺口未修复而拒绝。'
        '误报、当前 unknown 均 0；103 条后续归因 unknown 保留。负对照是明确测试注入，不冒充模型生成。','',
        '已存档的 107 场景结果上，B 在新门控下通过；D 仍因两条漏报未修复而拒绝。'
        'C 在原来不含搜索目标的历史范围内可以接受，但不代表它修复了 valid 缺口。'
        'research30 的原始决定、独立结果和冻结版本不变。','',
        '缺失原生日志、执行 unknown、证据身份改变、历史行缺失均被拒绝。'
        '另有实际合法事务的门控输入扰动测试，确认适用的历史触发丢失仍被拒绝；该测试不是新 RTL 运行。','',
        f"多种子状态：**{result['multiseed_status']}**。三个固定种子 3113/3119/3121，四组共 12 个预览请求，"
        '每组最多一次调用、无重试。每种子 A/C 提示相同、B/D 提示相同。'
        '105 个公共历史场景复用已验证记录，三种子各两条搜索见证重新原生验证；复用成本单列，不声称重新运行历史。','',
        '十二个提示在任何新调用前固定，每个种子四组均冻结后才生成其新独立输入；'
        '中途结果不改变其他种子的提示或候选。公开旧独立结果不再用作本轮独立结果；新测试不进入模型请求。','']
    if a.run:
        lines+=['| 组 | 接受次数/3（含 keep） | SVA 文本变化/3 | 搜索缺口补齐/3 | valid 独立验收/3 | 独立检出 | 独立漏报 | 独立误报 | 当前 unknown |',
                '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for n,r in run_result['summary'].items():
            t=r['independent'];lines.append(f"| {n} | {r['accepted']}/3 | {r['changed_sets']}/3 | "
                f"{r['acquired_gaps_fully_resolved']}/3 | {r['valid_boundaries_fully_detected']}/3 | "
                f"{t['detections']} | {t['misses']} | {t['false_positives']} | {t['unknown']} |")
        lines+=['','各种子原始结果和后续归因 unknown 见 multiseed_results.json，合计次数不是独立 Bug 数量。','',
                '| 种子 | 组 | 接受 | 历史检出丢失 | 历史新误报 | 独立检出/漏报 | 后续归因 unknown |',
                '|---|---|---|---:|---:|---:|---:|']
        for r in run_result['records']:
            t=r['independent']['counts']
            lines.append(f"| {r['seed']} | {r['arm']} | {r['decision']['accepted']} | "
                f"{len(r['lost_historical_detections'])} | {len(r['new_historical_false_positives'])} | "
                f"{t['detections']}/{t['misses']} | {t['later_attribution_unknown']} |")
        lines+=['','门控相对旧规则更正的准入决定：', '',
                f"`{run_result['gate_admission_corrections']}`。纠正无必要触发导致的拒绝，不自动等于修复了新目标。",'',
                f"实际进入原生历史门控的模型提案有 {run_result['gated_native_proposals']} 个；"
                f"因历史检出、适用触发或合法误报退化而拒绝的自然提案：`{run_result['natural_historical_regression_rejections']}`。"
                "列表为空意味着本批未观察到防退化保住历史保护的实际收益，不能用人为负对照代替这一实验结论。",'',
                '逐种子的 B−A、D−C、C−A、D−B 对比及 A/B 实际冻结候选的只读门控复算均已保存。'
                '各组模型可能返回不同表达式，不能把全部结果差异归因于单个机制；三次重复也不能支持广泛统计优势。','']
        lines+=['这里的 valid 验收只指两类边界的已曝光目标。各义务的触发和违例分母保存在独立结果 obligations 中；'
                '没有目标曝光的义务不能按通过处理，后续归因 unknown 也不被删除。没有全五义务或整个父案例通过的新结论。','']
        lines+=['每种子、每组两类边界的完整轨迹均在 case_examples.json：原始漏报、前后采样、已接受事务、模型原文、决定、冻结后的回放及独立结果。'
                'A/C 中的搜索案例仅在冻结后审计出现，未进入其模型提示。','']
        for r in run_result['records']:
            if r['changed_properties']:
                lines.append(f"种子 {r['seed']}，组 {r['arm']} 的实际接受修改：")
                for change in r['changed_properties']:
                    lines+=['```systemverilog',f"// before {change['id']}",change['before'],
                            '// after (model text)',change['after'],'```','']
    else:
        lines+=['上一轮四次远程额度已耗尽。此阶段没有发起新模型调用，12 次新授权仍是运行依赖；'
                '不能把请求已准备或本地验证通过写成多种子消融已完成。']
    lines+=['',f'实际本阶段成本：`{cost}`。金额不可用，形式化调用 0。','',
        '适用范围：一个已知 FIFO RTL 加人工输出故障任务的有限回放；'
        '新门控对其他义务缺少适用性证明时仍保守拒绝，没有全局防退化或跨父 Bug 结论。','',
        '```powershell',
        'wsl -- python3 scripts/research31_gate_validate.py --out deliverables/research31_gate_validation_NEW',
        'wsl -- python3 scripts/research31_multiseed.py prepare --validation deliverables/research31_gate_validation_20261020_r01 --out deliverables/research31_multiseed_prepare_NEW',
        '```','']
    (out/'SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    shutil.copy2(__file__,out/'report_source.py')
    print(dict(status=result['multiseed_status'],cost=cost),flush=True)


if __name__=='__main__':main()
