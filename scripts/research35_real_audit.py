"""Read-only provenance, gating, frozen identity and holdout audit for research35."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import research17_loop as loop
from research34_applicability import validate_plan,native_target_gate,portable
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
    for n,h in read(prep/'prepared_hashes.json').items():check('prepared:'+n,digest(prep/n)==h)
    for n,h in read(prep/'source_snapshot/hashes.json').items():check('source:'+n,digest(run/'source_snapshot'/n)==h)
    check('rtl_bound',digest(run/'axis_fifo.v')==digest(prep/'axis_fifo.v'))
    expected=read(prep/'expected.private.json');initial=read(prep/'shared_initial.json')
    request=read(prep/'request.preview.json');plans=[];plan=None;plan_ok=False
    for version in sorted((run/'plan').glob('v*')):
        folder=version/'model_call';actual=read(folder/'request.json');result=read(folder/'result.json')
        check(str(version.name)+':plan_request_is_actual_feedback',actual==request)
        plan=read(folder/'applicability_plan.json') if (folder/'applicability_plan.json').exists() else None
        if plan is not None:check(version.name+':plan_from_raw_response',raw_response(folder,plan))
        verdict=validate_plan(plan,expected);check(version.name+':plan_gate_recomputed',verdict==read(version/'decision.json'))
        check(version.name+':plan_no_retry',result['retries']==0)
        rows=[]
        for truth in expected:
            values=[r for r in (plan.get('windows',[]) if isinstance(plan,dict) else []) if isinstance(r,dict) and r.get('id')==truth['id']]
            value=values[0] if len(values)==1 else None
            rows.append(dict(id=truth['id'],category=truth['category'],actual=value,
                expected={k:truth[k] for k in ('anchor_cycle','check_cycle','applicability')},
                matched=bool(value and all(value.get(k)==truth[k] for k in ('anchor_cycle','check_cycle','applicability')))))
        binary=sum(bool(r['actual'] and r['actual'].get('applicability') in ('required','cancelled','not_required') and
            ((r['actual']['applicability']=='required')==(r['expected']['applicability']=='required')) and
            all(r['actual'].get(k)==r['expected'][k] for k in ('anchor_cycle','check_cycle'))) for r in rows)
        plans.append(dict(iteration=version.name,decision=verdict,matched=sum(r['matched'] for r in rows),
                          required_vs_not_required_diagnostic=binary,windows=rows,call=result))
        check(version.name+':no_calls_after_plan_accept',not plan_ok)
        plan_ok=verdict['accepted']
        body=json.loads(request['messages'][1]['content']);body.update(prior_actual_model_plan=plan,prior_actual_rejection=verdict)
        request=copy.deepcopy(request);request['messages'][1]['content']=json.dumps(body)
    check('bounded_plan_calls',1<=len(plans)<=2)
    current=initial;before=read(prep/'full_baseline.json');accepted_result=before;edits=[];examples=[];accepted=False
    if not plan_ok:check('no_sva_after_failed_plan',not (run/'sva').exists() and not list((run/'core').glob('v*')))
    else:
        for version in sorted((run/'core').glob('v*')):
            check(version.name+':no_edits_after_acceptance',not accepted)
            folder=version/'model_call';result=read(folder/'result.json');request=read(folder/'request.json')
            body=json.loads(request['messages'][1]['content'])
            check(version.name+':uses_verified_actual_plan',body['verified_model_applicability_plan']==plan)
            check(version.name+':sva_no_retry',result['retries']==0)
            edit=read(folder/'model_edit.json') if (folder/'model_edit.json').exists() else None
            candidate=read(folder/'candidate.json') if (folder/'candidate.json').exists() else None
            if edit is not None:check(version.name+':edit_from_raw_response',raw_response(folder,edit))
            if candidate is not None:check(version.name+':exact_operand_assembly',assemble(edit,initial)==candidate)
            decision=read(version/'decision.json');small=None;full=None
            if (version/'target_native/result.json').exists():
                small=read(version/'target_native/result.json')
                target=native_target_gate(read(prep/'target_baseline.json'),small,edit['assertion_id'])
                check(version.name+':target_gate_recomputed',target==read(version/'target_gate.json'))
                if target['accepted']:
                    full=read(version/'history_native/result.json')
                    verdict=gate.decide(before['group']['ledger'],full['group']['ledger'],sorted(loop.inspect(before['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False,reasons=[dict(kind='native_unavailable')])
                    verdict['accepted']=bool(verdict['accepted'] and full['healthy'])
                    check(version.name+':full_gate_recomputed',verdict['accepted']==decision['accepted'] and verdict['reasons']==decision['reasons'])
                else:
                    check(version.name+':target_failed_stops_full',not (version/'history_native').exists() and not decision['accepted'])
                old=loop.inspect(read(prep/'target_baseline.json')['group']['ledger'])
                new=loop.inspect(small['group']['ledger']) if small.get('group') else None
                for key in sorted(old['misses']):examples.append(dict(iteration=version.name,before=old['rows'][key],after=new['rows'].get(key) if new else None,edit=edit,decision=decision))
            else:check(version.name+':no_native_no_accept',not decision['accepted'])
            if decision['accepted']:current=candidate;accepted_result=full;accepted=True
            edits.append(dict(iteration=version.name,edit=edit,call=result,decision=decision,
                              target_metrics=metrics(small) if small and small.get('group') else None,
                              historical_metrics=metrics(full) if full and full.get('group') else None))
        check('bounded_sva_calls',1<=len(edits)<=2)
    final=read(run/'core/frozen_candidate.json');freeze=read(run/'core/freeze.json')
    check('freeze_is_accepted_or_rollback',final==current)
    check('hashes_match',loop.sha(final)==freeze['candidate_sha256']==outcome['frozen_hash'])
    check('acceptance_matches_outcome',accepted==outcome['accepted'])
    old=loop.inspect(before['group']['ledger']);new=loop.inspect(accepted_result['group']['ledger'])
    history=dict(detections_before=len(old['detections']),retained=len(old['detections']&new['detections']),
        lost=sorted(old['detections']-new['detections']),new_false_positives=sorted(new['false_positives']-old['false_positives']),
        scope='Accepted or retained state; baseline physical executions reused, not newly claimed.')
    independent=None
    if accepted:
        split=read(run/'independent/split.json');summary=read(run/'independent/summary.json');combined=read(run/'independent/combined.json')
        cases=split['boundary_cases']+split['drain_cases'];fresh={loop.sha(c['rows']) for c in cases}
        check('independent_after_freeze',(run/'independent/split.json').stat().st_mtime >= (run/'core/freeze.json').stat().st_mtime)
        check('independent_hash',split['frozen_hash']==loop.sha(final))
        check('independent_metrics_recomputed',metrics(combined)==summary['metrics'])
        exposed={loop.sha(c['rows']) for c in read(prep/'full_cases.json')}
        sources=read(loop.ROOT/'deliverables/research32_real_report_20261021_r02/results.json')['prior_exposed_inputs']
        paths=[portable(r['path']) for r in sources]+[loop.ROOT/f'deliverables/research{n}_real_20261021_r01/independent/split.json' for n in (32,33)]
        for path in paths:
            data=read(path);exposed.update([loop.sha(data)] if path.name=='stimulus.json' else [loop.sha(c['rows']) for c in (data if isinstance(data,list) else data['cases'])])
        check('independent_no_prior_input_overlap',not fresh&exposed)
        check('56_scenarios_48_inputs',len(cases)==summary['scenarios']==56 and len(fresh)==summary['distinct_inputs']==48)
        drain=read(run/'independent/drain_assessment.json')
        passed=combined['healthy'] and drain['passed'] and all(v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown')) for v in summary['metrics']['obligations'].values())
        check('five_obligation_criterion',passed==summary['all_five_pass_on_first_attributed_evidence'])
        independent=dict(**summary,drain_assessment=drain)
    else:check('no_holdout_after_rejected_candidate',not (run/'independent').exists())
    cost=cost_audit(run,artifacts(run));check('cost_crosscheck',all(cost['recorded_model_cost_crosscheck'].values()))
    check('call_budget_and_physical_attempts',cost['total']['model_calls']==outcome['calls']==len(list(run.rglob('attempt.json')))<=4)
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,outcome=outcome,plan_iterations=plans,
        sva_iterations=edits,historical_protection=history,independent=independent,cost=cost['total'],unused_calls=4-outcome['calls'],
        limitations='Single selected FIFO task with artificial faults; no cross-seed stability or global protection claim.')
    dump(out/'results.json',result);dump(out/'case_examples.json',examples);dump(out/'cost.json',cost)
    files=artifacts(run);manifest={p.relative_to(run).as_posix():digest(p) for p in files}
    dump(out/'run_manifest.json',manifest);assert all(digest(run/n)==h for n,h in manifest.items())
    shutil.copy2(__file__,out/'audit_source.py')
    lines=['# research35：真实适用性修正、细化与独立验收','',
        f"终态 {outcome['status']}。实际模型调用 {outcome['calls']}/4，未用 {4-outcome['calls']} 次。",'',
        '| 标注轮次 | 原三分类精确匹配 | 是否必须检查（诊断投影） | 接受 |','|---|---:|---:|---|']
    for p in plans:lines.append(f"| {p['iteration']} | {p['matched']}/13 | {p['required_vs_not_required_diagnostic']}/13 | {p['decision']['accepted']} |")
    lines+=['','是否必须检查只是事后诊断投影，不替换预先固定的三分类接受规则，也不补记为模型已通过第一关。错误标注、实际反馈和每个窗口的真值见 results.json/plan_iterations。']
    for p in plans:
        for r in p['windows']:
            if not r['matched']:lines.append(f"- {p['iteration']} / {r['id']} / {r['category']}：期望 {r['expected']}；实际 {r['actual']}。")
    for e in edits:
        lines+=['',f"SVA {e['iteration']}：接受 {e['decision']['accepted']}。",'```json',json.dumps(e['edit'],ensure_ascii=False,indent=2),'```',
            '拒绝原因：'+json.dumps([dict(kind=r['kind'],count=len(r.get('evidence_keys',[]))) for r in e['decision']['reasons']],ensure_ascii=False)]
    lines+=['',f"最终冻结：`{outcome['frozen_hash']}`。历史检出保留 {history['retained']}/{history['detections_before']}；新增历史误报 {len(history['new_false_positives'])}。拒绝版本不进入冻结集合。"]
    if independent:
        lines+=['',f"新独立输入 {independent['distinct_inputs']}，参数/故障场景 {independent['scenarios']}；五义务首个可归因证据验收 {independent['all_five_pass_on_first_attributed_evidence']}。",'',
            '| 义务 | 触发 | 检出 | 漏报 | 误报 | 当前unknown |','|---|---:|---:|---:|---:|---:|']
        for o,c in independent['metrics']['obligations'].items():lines.append(f"| {o} | {c['triggers']} | {c['detections']} | {c['misses']} | {c['false_positives']} | {c['unknown']} |")
        lines+=['','整体采样计数：'+json.dumps(independent['metrics']['counts'],ensure_ascii=False)]
    else:lines+=['','本轮未执行新的独立测试，不能算独立通过。']
    c=cost['total'];lines+=['',f"输入/输出tokens {c['prompt_tokens_total']}/{c['completion_tokens_total']}；原生编译 {c['native_compile_calls']}，执行 {c['native_execute_calls']}（含冒烟 {c['compile_smoke_execute_calls']}）；形式化0，金额不可用。",
        f"审计 {sum(c['passed'] for c in checks)}/{len(checks)}，核验 {len(manifest)} 个运行文件。审计通过不等于修复成功。",'',
        '所有检出和漏报计数为义务×采样证据行，不是独立Bug数。通过有限回放不能证明全局保护，后续归因unknown保留。单任务成功不能证明稳定多种子细化或机制优越性。','',
        '实际命令（已执行；不要重复消耗授权调用）：','```powershell',
        f'wsl -- python3 scripts/research35_campaign.py run --prepared {prep.relative_to(loop.ROOT).as_posix()} --out {run.relative_to(loop.ROOT).as_posix()} --authorization {prep.relative_to(loop.ROOT).as_posix()}/authorization.json','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(dict(passed=result['passed'],checks=len(checks),status=outcome['status'],calls=outcome['calls']))
    assert result['passed'],'audit_failed'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
