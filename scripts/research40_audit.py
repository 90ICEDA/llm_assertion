"""Audit exact archived model AST, unchanged gates and frozen fresh tests."""
import argparse
import json
from pathlib import Path
import shutil

import research17_loop as loop
import research31_gate as gate
import research40_interface_continuation as experiment
from research28_report import raw_response
from research29_drain import assess
from research30_ablation_report import metrics
from research34_applicability import native_target_gate,portable
from research34_campaign import digest
from research17_report import artifacts,cost_audit

read,dump=loop.read,loop.dump


def audit(run,out):
    outcome=read(run/'outcome.json')
    out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(name,value): checks.append(dict(name=name,passed=bool(value)))
    for name,h in read(run/'source_snapshot/hashes.json').items():
        check('source:'+name,digest(run/'source_snapshot'/name)==h)
    protocol=read(run/'protocol.json')
    source=portable(protocol['source'])
    edit=read(source/'model_edit.json')
    initial=read(run/'shared_initial.json')
    candidate=read(run/'candidate.json')
    check('actual_model_stream',raw_response(source,edit))
    check('source_edit_hash',digest(source/'model_edit.json')==protocol['source_sha256'])
    check('exact_ast_preserved',edit==read(run/'source_model_edit.json'))
    check('syntax_only_assembly',experiment.assemble(edit,initial)==candidate)
    check('unchanged_other_properties',all(a==b for a,b in zip(initial['assertions'],candidate['assertions']) if a['id']!=edit['assertion_id']))
    check('original_schema_rejection_not_relabelled',read(source.parent/'decision.json')['accepted'] is False)
    check('interface_qualified',read(run/'interface_qualification/result.json')['passed'])
    check('source_fixed_before_replay',(run/'protocol.json').stat().st_mtime<=(run/'target_native/result.json').stat().st_mtime)
    before=read(experiment.PREP/'full_baseline.json')
    small=read(run/'target_native/result.json')
    target=native_target_gate(read(experiment.PREP/'target_baseline.json'),small,edit['assertion_id'])
    check('target_gate_unchanged',target==read(run/'target_gate.json'))
    full=None
    if (run/'history_native/result.json').exists():
        full=read(run/'history_native/result.json')
        historical=gate.decide(before['group']['ledger'],full['group']['ledger'],sorted(loop.inspect(before['group']['ledger'])['misses']))
        historical['accepted']=bool(historical['accepted'] and full['healthy'])
        check('history_after_target',target['accepted'])
        check('historical_gate_unchanged',historical==read(run/'historical_gate.json'))
        check('acceptance_unchanged',outcome['accepted']==historical['accepted'])
    else: check('no_history_no_accept',not outcome['accepted'])
    frozen=read(run/'core/frozen_candidate.json')
    check('freeze_matches_decision',frozen==(candidate if outcome['accepted'] else initial))
    check('freeze_hash',loop.sha(frozen)==outcome['frozen_hash']==read(run/'core/freeze.json')['candidate_sha256'])
    old=loop.inspect(before['group']['ledger'])
    new=loop.inspect(full['group']['ledger']) if full and outcome['accepted'] else old
    history=dict(scenarios=len(read(experiment.PREP/'full_cases.json')),replayed=full is not None,
        before_detections=len(old['detections']),retained=len(old['detections']&new['detections']),
        lost=len(old['detections']-new['detections']),new_false_positives=len(new['false_positives']-old['false_positives']),
        current_unknown=len(new['unknown']))
    examples=[]
    old_target=loop.inspect(read(experiment.PREP/'target_baseline.json')['group']['ledger'])
    new_target=loop.inspect(small['group']['ledger'])
    for key in sorted(old_target['misses']):
        row=new_target['rows'][key]
        record=read(portable(row['source_directory'])/'replay.json')
        control=read(portable(row['source_directory']).parent/'correct/replay.json')
        examples.append(dict(before=old_target['rows'][key],after=row,
            samples=[s for s in record['reference_trace'] if s['cycle'] in (row['cycle']-1,row['cycle'])],
            correct_samples=[s for s in control['reference_trace'] if s['cycle'] in (row['cycle']-1,row['cycle'])],
            original_property=next(a['property'] for a in initial['assertions'] if a['id']==edit['assertion_id']),
            model_property=next(a['property'] for a in candidate['assertions'] if a['id']==edit['assertion_id'])))
    independent=None
    if outcome['accepted']:
        split=read(run/'independent/split.json')
        independent=read(run/'independent/summary.json')
        cases=split['boundary_cases']+split['drain_cases']
        fresh={loop.sha(c['rows']) for c in cases}
        exposed={loop.sha(c['rows']) for c in read(experiment.PREP/'full_cases.json')}
        paths=[portable(r['path']) for r in read(loop.ROOT/'deliverables/research32_real_report_20261021_r02/results.json')['prior_exposed_inputs']]
        paths += [loop.ROOT/f'deliverables/research{n}_real_20261021_r01/independent/split.json' for n in (32,33)]
        for p in paths:
            value=read(p)
            exposed.update([loop.sha(value)] if p.name=='stimulus.json' else [loop.sha(c['rows']) for c in (value if isinstance(value,list) else value['cases'])])
        check('fresh_inputs_no_development_overlap',not fresh&exposed)
        check('independent_generated_after_freeze',(run/'independent/split.json').stat().st_mtime>=(run/'core/freeze.json').stat().st_mtime)
        check('independent_frozen_hash',split['frozen_hash']==loop.sha(frozen))
        check('independent_sizes',len(cases)==independent['scenarios']==56 and len(fresh)==independent['distinct_inputs']==48)
        check('all_test_replays_exact_frozen_candidate',all(read(p)['candidate']==frozen for p in (run/'independent').rglob('replay.json')))
        combined=read(run/'independent/combined.json')
        check('independent_metrics',metrics(combined)==independent['metrics'])
        drain=assess(run/'independent/drain',split['drain_cases'],read(run/'independent/drain/result.json'))
        check('drain_reassessment',drain==read(run/'independent/drain_assessment.json'))
        passing=combined['healthy'] and drain['passed'] and all(m['detections']>0 and m['triggers']>0 and not any(m[k] for k in ('misses','false_positives','unknown')) for m in independent['metrics']['obligations'].values())
        check('unchanged_five_obligation_acceptance',passing==independent['all_five_pass_on_first_attributed_evidence'])
    else: check('no_test_for_rejected_candidate',not (run/'independent').exists())
    cost=cost_audit(run,artifacts(run))
    check('no_new_model_calls',cost['total']['model_calls']==outcome['model_calls']==0)
    source_cost=read(loop.ROOT/'deliverables/research39_real_report_20261022_r01/cost.json')['total']
    auxiliary=[read(run/'interface_qualification/four_state_boolean'/name) for name in
        ('expression_tool_version.json','expression_compile.json','expression_execute.json')]
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,outcome=outcome,
        model_origin=str(source),source_schema_rejected=True,interface_continuation=True,
        source_model_cost=source_cost,cost=cost['total'],auxiliary_expression_commands=auxiliary,
        target_gate=target,target_metrics=metrics(small),history=history,
        history_metrics=metrics(full) if full else None,independent=independent)
    dump(out/'results.json',result);dump(out/'case_examples.json',examples);dump(out/'cost.json',cost)
    dump(out/'run_manifest.json',{p.relative_to(run).as_posix():digest(p) for p in artifacts(run)})
    shutil.copy2(__file__,out/'audit_source.py')
    prop=next(a['property'] for a in candidate['assertions'] if a['id']==edit['assertion_id'])
    oldprop=next(a['property'] for a in initial['assertions'] if a['id']==edit['assertion_id'])
    lines=['# research39–40：真实模型响应的接口续验','',
        f"记录复核通过 {sum(c['passed'] for c in checks)}/{len(checks)}；research40 状态 `{outcome['status']}`。",'',
        'research39 两次真实调用均按原 schema 拒绝，未原生执行。research40 为另立的接口扩展续验：固定选用最新 v1 原始响应，在新增多项逻辑与和显式 rst 支持后重新执行。未删去 rst、未替换条件/数据/运算符/时序，未额外调用模型。不能将 research39 原试验改记为接受，也不是新接口下的重新生成或多种子稳定性结果。','',
        '主案例为真实 axis_fifo RTL 加人工边界故障，不能计为真实上游历史修复成功。接受标准仍为原生目标和历史保护门控，关键 unknown 拒绝。','',
        '原 a2：','```systemverilog',oldprop,'```','模型生成的 a2（仅语法渲染）：','```systemverilog',prop,'```','',
        f"目标回放通过：{target['accepted']}，共 {len(target['target_rows'])} 条原漏报。完整历史 {history['scenarios']} 场景，回放 {history['replayed']}，检出保留 {history['retained']}/{history['before_detections']}，丢失 {history['lost']}，新增误报 {history['new_false_positives']}，当前 unknown {history['current_unknown']}。",'',
        f"冻结哈希 `{outcome['frozen_hash']}`。"]
    chosen=[]
    for family in ('long_valid_withdraw_stalled','long_valid_withdraw_release'):
        ex=next((e for e in examples if e['after']['variant']==family),None)
        if ex: chosen.append(ex)
    for ex in chosen:
        row=ex['after'];samples=ex['samples'];fixed=ex['correct_samples']
        lines += ['',f"实际开发见证 `{row['scenario_id']}` / `{row['variant']}`，检查周期 {row['cycle']}：",'',
            '```json',json.dumps(dict(faulty_samples=samples,correct_samples=fixed,
                before_native=ex['before']['native']['assertions'],after_native=row['native']['assertions'],
                independent_oracle=row['oracle']),ensure_ascii=False,indent=2),'```']
    if independent:
        lines += ['',f"冻结后独立测试 {independent['scenarios']} 场景、{independent['distinct_inputs']} 种激励。五项义务在首个可归因证据上通过：{independent['all_five_pass_on_first_attributed_evidence']}。",'',
            '| 义务 | 检出 | 漏报 | 误报 | 当前 unknown | 触发 |','|---|---:|---:|---:|---:|---:|']
        for ob,m in independent['metrics']['obligations'].items():
            lines.append(f"| {ob} | {m['detections']} | {m['misses']} | {m['false_positives']} | {m['unknown']} | {m['triggers']} |")
        lines += ['', '完整计数（包含后续归因 unknown，不删除）：','```json',json.dumps(independent['metrics']['counts'],ensure_ascii=False,indent=2),'```']
    else: lines += ['','无新接受版本，独立测试未执行。']
    lines += ['', '逐条模型 AST、两次真实响应、原生事务样本和修改前后证据见 `case_examples.json`、`results.json` 及运行目录。','',
        f"research39 实际模型调用 {source_cost['model_calls']}，输入/输出 tokens {source_cost['prompt_tokens_total']}/{source_cost['completion_tokens_total']}，新增授权全部用完。research40 新模型调用 0，原生编译 {cost['total']['native_compile_calls']}、执行 {cost['total']['native_execute_calls']}（含 {cost['total']['compile_smoke_execute_calls']} 次冒烟），另有 3 次四态表达式诊断命令。形式化 0，金额不可用。",'',
        '有限场景检出不构成形式化证明；历史保护保持仅适用于已回放证据。首个可归因证据通过不能扩展为全部后续违例均有因果归因，或整个真实历史父案例通过。','',
        '```powershell',
        '# 本轮实际执行过的续验命令；输出目录已有记录，不覆盖。',
        'wsl -- python3 scripts/research40_interface_continuation.py --out deliverables/research40_interface_continuation_20261022_r01',
        '# 只读复核，使用新报告目录，不调用模型或重新仿真。',
        'wsl -- python3 scripts/research40_audit.py --run deliverables/research40_interface_continuation_20261022_r01 --out deliverables/research40_report_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(dict(passed=result['passed'],checks=len(checks),accepted=outcome['accepted'],independent=bool(independent)),flush=True)
    assert result['passed'],'audit_failed'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
