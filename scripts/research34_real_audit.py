"""Read-only verification of actual applicability -> SVA -> native stage gates."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import research17_loop as loop
from research34_applicability import certificate,validate_plan,native_target_gate,portable
from research28_report import raw_response
from research32_model import assemble
from research17_report import cost_audit,artifacts
from research30_ablation_report import metrics
import research31_gate as gate


def audit(prep,run,out):
    read,dump=loop.read,loop.dump
    outcome=read(run/'outcome.json');out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(name,value):checks.append(dict(name=name,passed=bool(value)))
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    protocol=read(prep/'protocol.json');initial=read(prep/'shared_initial.json')
    for name,h in protocol['source_hashes'].items():check('executed_source:'+name,digest(run/'source_snapshot'/name)==h)
    for name,h in read(prep/'prepared_hashes.json').items():check('prepared_binding:'+name,digest(prep/name)==h)
    check('rtl_content_bound',digest(run/'axis_fifo.v')==digest(prep/'axis_fifo.v'))
    expected=read(prep/'applicability.expected.private.json')
    for row in expected:
        path=portable(row['source']);cert=certificate(read(path),row['check_cycle'])
        check(row['id']+':independent_recompute',all(row[k]==cert[k] for k in cert) and digest(path)==row['source_sha256'])
    folder=run/'plan/model_call';request=read(folder/'request.json');call=read(folder/'result.json')
    check('first_request_exactly_preview',request==read(prep/'plan_request.preview.json'))
    check('plan_call_not_sva_generation',call['output_kind']=='applicability_plan' and not (folder/'candidate.sva').exists())
    check('plan_no_retry',call['retries']==0)
    plan=read(folder/'applicability_plan.json') if (folder/'applicability_plan.json').exists() else None
    if plan is not None:check('raw_response_matches_plan',raw_response(folder,plan))
    verdict=validate_plan(plan,expected);check('plan_gate_recalculation',verdict==read(run/'plan/decision.json'))
    rows=[]
    supplied=plan.get('windows',[]) if isinstance(plan,dict) else []
    for truth in expected:
        matches=[r for r in supplied if isinstance(r,dict) and r.get('id')==truth['id']]
        actual=matches[0] if len(matches)==1 else None
        fields=('anchor_cycle','check_cycle','applicability')
        rows.append(dict(id=truth['id'],category=truth['category'],expected={k:truth[k] for k in fields},actual=actual,
                         matched=bool(actual and all(actual.get(k)==truth[k] for k in fields)),samples=truth['samples']))
    accepted=initial;stage2=None;small=None;full=None;independent=None
    if not verdict['accepted']:
        check('stopped_before_second_call',not (run/'sva').exists())
        check('no_native_or_holdout_after_failed_plan',not (run/'core/target_native').exists() and not (run/'independent').exists())
        check('correct_early_stop_status',outcome['status']=='applicability_rejected_no_sva_generation')
    else:
        folder=run/'sva/model_call';result=read(folder/'result.json');request=read(folder/'request.json')
        check('stage2_after_plan_pass',(folder/'attempt.json').stat().st_mtime >= (run/'plan/decision.json').stat().st_mtime)
        body=json.loads(request['messages'][1]['content'])
        check('stage2_uses_exact_verified_model_plan',body['verified_model_applicability_plan']==plan)
        check('stage2_no_retry',result['retries']==0)
        edit=read(folder/'model_edit.json') if (folder/'model_edit.json').exists() else None
        candidate=read(folder/'candidate.json') if (folder/'candidate.json').exists() else None
        if edit is not None:check('raw_response_matches_sva_edit',raw_response(folder,edit))
        if candidate is not None:check('no_semantic_predicate_rewrite',assemble(edit,initial)==candidate)
        stage2=dict(call=result,edit=edit,proposal_hash=loop.sha(candidate) if candidate else None)
        if (run/'core/target_native/result.json').exists():
            before_binding=read(prep/'baseline_binding.json');path=portable(before_binding['path'])
            check('target_baseline_bound',digest(path)==before_binding['sha256'])
            replay=read(run/'core/target_native/result.json')
            decision=native_target_gate(read(path),replay,edit['assertion_id'])
            check('native_target_gate_recalculation',decision==read(run/'core/target_gate.json'))
            small=dict(decision=decision,metrics=metrics(replay) if replay.get('group') else None)
            if not decision['accepted']:
                check('target_failure_stops_full_history',not (run/'core/history_native').exists())
                check('target_failure_retains_initial',outcome['status']=='native_target_gate_rejected_before_full_history')
            else:
                binding=read(loop.ROOT/'deliverables/research33_prepare_20261021_r02/s3203/baseline_binding.json')
                path=portable(binding['result_path']);check('full_baseline_bound',digest(path)==binding['result_sha256'])
                old=read(path);replay=read(run/'core/history_native/result.json')
                computed=gate.decide(old['group']['ledger'],replay['group']['ledger'],sorted(loop.inspect(old['group']['ledger'])['misses'])) if replay.get('group') else dict(accepted=False,reasons=[dict(kind='native_unavailable')])
                computed['accepted']=bool(computed['accepted'] and replay['healthy'])
                saved=read(run/'core/decision.json')
                check('full_history_gate_recalculation',computed['accepted']==saved['accepted'] and computed['reasons']==saved['reasons'])
                full=dict(decision=saved,metrics=metrics(replay) if replay.get('group') else None)
                if saved['accepted']:accepted=candidate
        else:check('unusable_proposal_stops_before_native',not (run/'core/history_native').exists())
    final=read(run/'core/frozen_candidate.json');freeze=read(run/'core/freeze.json')
    check('final_is_accepted_or_retained_state',final==accepted)
    check('freeze_hash_consistent',loop.sha(final)==freeze['candidate_sha256']==outcome['frozen_hash'])
    if (run/'independent/split.json').exists():
        split=read(run/'independent/split.json');fresh={loop.sha(c['rows']) for c in split['cases']}
        check('independent_after_freeze',(run/'independent/split.json').stat().st_mtime >= (run/'core/freeze.json').stat().st_mtime)
        check('independent_frozen_candidate',split['frozen_hash']==loop.sha(final))
        exposed=set()
        old_paths=[portable(x['path']) for x in read(loop.ROOT/'deliverables/research32_real_report_20261021_r02/results.json')['prior_exposed_inputs']]
        old_paths += [loop.ROOT/'deliverables'/f'research{n}_real_20261021_r01/independent/split.json' for n in (32,33)]
        old_paths.append(loop.ROOT/'deliverables/research33_prepare_20261021_r02/s3203/cases.json')
        for path in old_paths:
            data=read(path)
            if path.name=='stimulus.json':exposed.add(loop.sha(data))
            else:exposed.update(loop.sha(c['rows']) for c in (data if isinstance(data,list) else data['cases']))
        check('independent_no_exposed_inputs',not fresh&exposed)
        replay=read(run/'independent/native/result.json')
        independent=dict(seed=split['seed'],distinct_inputs=len(fresh),parameter_fault_scenarios=len(split['cases']),metrics=metrics(replay) if replay.get('group') else None)
    costs=cost_audit(run,artifacts(run));check('cost_records_match',all(costs['recorded_model_cost_crosscheck'].values()))
    attempts=list(run.rglob('attempt.json'))
    check('bounded_actual_calls',len(attempts)==costs['total']['model_calls']==outcome['model_calls']<=2)
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,outcome=outcome,plan_verdict=verdict,
                window_results=rows,matched_windows=sum(r['matched'] for r in rows),stage2=stage2,
                native_target=small,full_history=full,independent=independent,cost=costs['total'],
                unused_authorized_calls=2-len(attempts),whole_case_protected=False,
                scope='Single targeted model trial; window-label correctness is not global specification understanding or SVA correctness.')
    dump(out/'results.json',result);dump(out/'cost.json',costs)
    files=artifacts(run);manifest={p.relative_to(run).as_posix():digest(p) for p in files}
    dump(out/'run_manifest.json',manifest);assert all(digest(run/n)==h for n,h in manifest.items())
    shutil.copy2(__file__,out/'audit_source.py')
    lines=['# research34：真实模型分阶段验收','',
           f"终态：{outcome['status']}。实际调用 {len(attempts)}/2，未使用 {2-len(attempts)} 次。无传输重试。",
           f"适用周期逐窗口匹配 {result['matched_windows']}/{len(rows)}，第一关整体通过：{verdict['accepted']}。",'',
           '| 窗口 | 类型 | 前置→检查周期 | 独立判定 | 模型标注 | 匹配 |','|---|---|---|---|---|---|']
    for r in rows:
        e=r['expected'];a=r['actual'] or {}
        lines.append(f"| {r['id']} | {r['category']} | {e['anchor_cycle']}→{e['check_cycle']} | {e['applicability']} | {a.get('applicability','missing')} ({a.get('anchor_cycle')}→{a.get('check_cycle')}) | {r['matched']} |")
    lines+=['',f"SVA生成：{'已执行' if stage2 else '未执行'}；小批原生：{'已执行' if small else '未执行'}；完整历史：{'已执行' if full else '未执行'}；新独立测试：{'已执行' if independent else '未执行'}。",
            f"冻结哈希：`{outcome['frozen_hash']}`；新修改接受：{outcome['accepted']}。"]
    if stage2 and stage2['edit']:lines+=['','模型原始编辑：','```json',json.dumps(stage2['edit'],indent=2,ensure_ascii=False),'```']
    if small:lines+=['',f"目标原生门控通过：{small['decision']['accepted']}；原因见 results.json/native_target。",json.dumps(small['metrics']['counts'] if small['metrics'] else None,ensure_ascii=False)]
    if independent:lines+=['',f"新独立输入 {independent['distinct_inputs']} 条、参数/故障场景 {independent['parameter_fault_scenarios']} 个。",json.dumps(independent['metrics'],ensure_ascii=False)]
    c=costs['total']
    lines+=['',f"输入/输出 tokens：{c['prompt_tokens_total']}/{c['completion_tokens_total']}；原生编译 {c['native_compile_calls']}，执行 {c['native_execute_calls']}（含编译冒烟）；形式化0，金额不可用。",
            f"记录与一致性检查 {sum(c['passed'] for c in checks)}/{len(checks)}；产物哈希核验 {len(manifest)} 个文件。审计通过不等于模型修复成功。",'',
            '只有已执行的阶段可以报告结果。拒绝时保留原候选；未执行独立测试不等于独立通过。有限回放不构成全局保护或形式化证明。','',
            '实际执行命令（已用调用不允许重复提交）：','```powershell',
            f'wsl -- python3 scripts/research34_campaign.py run --prepared {prep.relative_to(loop.ROOT).as_posix()} --out {run.relative_to(loop.ROOT).as_posix()} --authorization {prep.relative_to(loop.ROOT).as_posix()}/authorization.json','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(dict(passed=result['passed'],checks=len(checks),status=outcome['status'],calls=len(attempts),matched=result['matched_windows']))
    assert result['passed'],'audit_failed'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
