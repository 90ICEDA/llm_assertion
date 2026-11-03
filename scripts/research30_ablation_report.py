"""Post-freeze audit of the controlled 2x2 real-model experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import research17_loop as loop
import research17_report as cost_tools
from research28_report import raw_response
from research30_ablation import ARMS,Model

read,dump=loop.read,loop.dump


def portable(value):
    text=str(value).replace('\\','/')
    marker='/AssertionForge-main1/'
    return loop.ROOT/text.split(marker,1)[1] if marker in text else Path(text)


def metrics(result):
    info=loop.inspect(result['group']['ledger'])
    scenarios={row['scenario_id'] for row in info['rows'].values()}
    exposed={info['rows'][key]['scenario_id'] for key in info['detections']|info['misses']}
    return dict(healthy=result['healthy'],counts=result['counts'],
        scenarios_total=len(scenarios),scenarios_with_first_attributable_target=len(exposed),
        scenarios_without_first_attributable_target=sorted(scenarios-exposed),
        obligations={o:{k:sum(info['rows'][x]['obligation']==o for x in info[k])
            for k in ('detections','misses','unknown','false_positives','triggers')} for o in loop.model.SPECS})


def trigger_applicability(row):
    """Diagnostic only; never changes the preregistered gate decision."""
    source=portable(row['source_directory'])/'replay.json'
    replay=read(source);cycle=row['cycle']
    samples={s['cycle']:s for s in replay['reference_trace']}
    before,now=samples.get(cycle-1),samples.get(cycle)
    checks=[c for c in replay['oracle']['checks'] if c['cycle']==cycle and c['obligation']==row['obligation']]
    status='unknown'
    if replay['sampling_qualification']['status']=='passed' and replay['oracle']['legality']=='legal':
        if checks:
            status='independent_obligation_check_present'
        elif row['obligation']=='stall_stability' and before and now and before['rst']==1 and now['rst']==0:
            status='not_required_previous_reset_cancelled_stall_obligation'
    return dict(evidence_id=row['evidence_id'],status=status,obligation=row['obligation'],cycle=cycle,
        samples=[before,now],independent_checks=checks,source=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        scope='Post hoc explanation only; no historical evidence deletion, changed acceptance or changed frozen candidate.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    run=a.run.resolve();outcome=read(run/'outcome.json')
    assert outcome['status']=='four_real_model_arms_completed'
    prep=portable(read(run/'prepared_source.json')['path'])
    baseline=read(prep/'core/history/result.json')
    old=loop.inspect(baseline['group']['ledger'])
    initial=read(run/'shared_initial.json')
    report=run/'report';report.mkdir(exist_ok=True)
    files=[p for p in run.rglob('*') if p.is_file() and 'report' not in p.relative_to(run).parts]
    cost=cost_tools.cost_audit(run,files);dump(report/'cost.json',cost)
    records={};requests={};integrity=[]
    for name,arm in ARMS.items():
        folder=run/'arms'/name
        requests[name]=read(folder/'model_call/request.json')
        final=read(folder/'frozen_candidate.json')
        decision=read(folder/'decision.json')
        entry=dict(settings=arm,decision=decision,frozen_hash=loop.sha(final),
            changed_properties=[dict(id=b['id'],before=x['property'],after=b['property']) for x,b in zip(initial['assertions'],final['assertions']) if x['property']!=b['property']])
        call=folder/'model_call'
        assembled=None;raw_ok=None
        entry['model_call_result']=read(call/'result.json')
        if (call/'model_edit.json').exists():
            edit=read(call/'model_edit.json')
            entry['model_edit']=edit
            raw_ok=raw_response(call,edit)
        if (call/'candidate.json').exists():
            assembled=Model.edit(edit,initial)
            raw_ok=raw_ok and assembled==read(call/'candidate.json')
        expected=assembled if decision['accepted'] else initial
        okay=expected==final and loop.sha(final)==read(folder/'freeze.json')['candidate_sha256'] and raw_ok is not False
        integrity.append(dict(arm=name,passed=okay,raw_response_match=raw_ok))
        history=read(run/'historical_audit'/name/'result.json')
        hist=loop.inspect(history['group']['ledger'])
        entry['historical_audit']=metrics(history)
        entry['historical_preservation']=dict(
            original_detections=len(old['detections']),
            lost_original_detections=sorted(old['detections']-hist['detections']),
            lost_original_triggers=sorted(old['triggers']-hist['triggers']),
            new_original_false_positives=sorted((hist['false_positives'] & old['rows'].keys())-old['false_positives']),
            remaining_search_misses=sorted(hist['misses']))
        entry['lost_historical_trigger_applicability']=[trigger_applicability(old['rows'][k])
            for k in sorted(old['triggers']-hist['triggers'])]
        gate_path=folder/'historical_gate.json'
        if gate_path.exists():
            gate=read(gate_path)
            before_rows={r['evidence_id']:r for r in read(folder/'before/result.json')['group']['ledger']}
            entry['gate_trigger_rejection_applicability']=[
                trigger_applicability(before_rows[k]) for reason in gate['reasons']
                if reason['kind']=='lost_obligation_trigger' for k in reason['evidence_keys']]
        entry['independent']=metrics(read(run/'independent'/name/'result.json'))
        call_result=entry['model_call_result']
        entry['cost']=dict(prompt_tokens=call_result.get('prompt_tokens'),
            completion_tokens=call_result.get('completion_tokens'),
            model_wall_seconds=call_result.get('wall_seconds'),
            native_by_stage={stage:dict(
                compiles=sum(c['kind']=='compile' and c['path'].startswith(prefix) for c in cost['native_commands']),
                executions=sum(c['kind']=='execute' and c['path'].startswith(prefix) for c in cost['native_commands']))
                for stage,prefix in (('decision',f'arms/{name}/'),('post_freeze_history',f'historical_audit/{name}/'),
                                     ('independent',f'independent/{name}/'))})
        records[name]=entry
    freeze=read(run/'all_arms_freeze.json');split=read(run/'independent/split.json')
    dev=read(prep/'history_cases.json')+read(prep/'acquired_cases.json')
    checks=dict(initial_matches_prepared=initial==read(prep/'shared_initial.json'),
        initial_requests_A_C_equal=requests['A']==requests['C'],initial_requests_B_D_equal=requests['B']==requests['D'],
        actual_requests_match_previews=all(requests[n]==read(prep/'preview'/n/'request.preview.json') for n in ARMS),
        all_final_sets_match_model_decisions=all(x['passed'] for x in integrity),
        exactly_four_actual_calls=cost['total']['model_calls']==4,
        independent_after_all_freeze=(run/'independent/split.json').stat().st_mtime>=(run/'all_arms_freeze.json').stat().st_mtime,
        final_hashes_bound=freeze==split['hashes']=={n:r['frozen_hash'] for n,r in records.items()},
        no_development_input_overlap=not ({loop.sha(c['rows']) for c in dev}&{loop.sha(c['rows']) for c in split['cases']}),
        source_snapshots_valid=all(hashlib.sha256((run/'source_snapshot'/n).read_bytes()).hexdigest()==h
            for n,h in read(run/'source_snapshot/hashes.json').items()))
    # Do not manufacture a mechanism advantage from successful individual arms.
    same_independent=len({json.dumps(v['independent']['counts'],sort_keys=True) for v in records.values()})==1
    same_preservation=len({json.dumps({k:x for k,x in v['historical_preservation'].items()
        if k!='remaining_search_misses'},sort_keys=True) for v in records.values()})==1
    contrasts={}
    for label,left,right in (('search_without_gate','B','A'),('search_with_gate','D','C'),
                             ('gate_without_search','C','A'),('gate_with_search','D','B')):
        contrasts[label]=dict(treatment=left,control=right,
            independent_delta={metric:records[left]['independent']['counts'][metric]-records[right]['independent']['counts'][metric]
                for metric in ('detections','misses','false_positives','unknown')},
            lost_historical_detections_delta=len(records[left]['historical_preservation']['lost_original_detections'])-
                len(records[right]['historical_preservation']['lost_original_detections']))
    from research15_evidence import merge_ledgers
    baseline_all=merge_ledgers([baseline['group'],read(prep/'core/acquired/result.json')['group']])
    baseline_info=loop.inspect(baseline_all['ledger'])
    b_history=read(run/'historical_audit/B/result.json')
    counterfactual_b=loop.decide(baseline_all['ledger'],b_history['group']['ledger'],sorted(baseline_info['misses']))
    dump(report/'counterfactual_gate_on_B.json',dict(gate=counterfactual_b,
        scope='Read-only gate replay of the actual B frozen candidate over already executed common history+search evidence. Not an extra model arm or changed acceptance.',
        trigger_applicability=[trigger_applicability(baseline_info['rows'][k])
            for reason in counterfactual_b['reasons'] if reason['kind']=='lost_obligation_trigger'
            for k in reason['evidence_keys']]))
    acquired_info=loop.inspect(read(prep/'core/acquired/result.json')['group']['ledger'])
    b_audit=loop.inspect(b_history['group']['ledger'])
    independent_info={n:loop.inspect(read(run/'independent'/n/'result.json')['group']['ledger'])
                      for n in ARMS}
    examples=[]
    for key in sorted(acquired_info['misses']):
        row=acquired_info['rows'][key]
        source=portable(row['source_directory'])/'replay.json'
        replay=read(source)
        cycle=row['cycle']
        transactions=[t for t in replay['oracle']['transactions']
            if t['accept_cycle']<cycle and
            (t.get('response_cycle') is None or t['response_cycle']>=cycle) and
            (t.get('cancel_cycle') is None or t['cancel_cycle']>cycle)]
        examples.append(dict(mechanism=row['variant'],original_miss=row,
            native_samples=[x for x in replay['reference_trace'] if cycle-1<=x['cycle']<=cycle],
            accepted_uncompleted_transactions_at_violation=transactions,
            transaction_mapping_scope='Pending transactions before the sampled edge: accept_cycle < violation cycle, response_cycle >= violation cycle. Same-edge presented input is not counted as already accepted. Port stability check itself has no single transaction_id.',
            after_B=b_audit['rows'][key],final_B_hash=records['B']['frozen_hash'],
            source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            independent_by_arm={n:{metric:sum(
                info['rows'][k]['variant']==row['variant'] and info['rows'][k]['obligation']==row['obligation']
                for k in info[metric]) for metric in ('detections','misses','false_positives','unknown')}
                for n,info in independent_info.items()}))
    dump(report/'case_examples.json',examples)
    result=dict(arms=records,integrity=integrity,checks=checks,cost=cost['total'],
        concrete_examples=examples,
        independent_seed=split['seed'],independent_cases=len(split['cases']),
        identical_observed_independent_counts=same_independent,
        identical_observed_historical_preservation=same_preservation,
        observed_contrasts=contrasts,
        counterfactual_gate_on_B=dict(accepted=counterfactual_b['accepted'],
            reasons=[dict(kind=r['kind'],count=len(r.get('evidence_keys',[]))) for r in counterfactual_b['reasons']]),
        same_prompt_output_equality=dict(A_C=records['A'].get('model_edit')==records['C'].get('model_edit'),
                                        B_D=records['B'].get('model_edit')==records['D'].get('model_edit')),
        interpretation='No measurable outcome benefit in this pilot if all arms tie; gate rejection or search effect must come from actual differences. One model seed/one task does not establish stability.',
        search_cost=dict(source=str(read(prep/'protocol.json')['source_search_cost']),physical_shared_native_executions=64,logical_native_executions_per_search_arm=64),
        scope='Known synthetic FIFO fault task; genuine models and native replay. Historical/no-regression guarantees are limited to actual evidence, not global.')
    dump(report/'results.json',result)
    lines=['# Research30：四组真实模型消融','',
        'A 普通反馈；B 加搜索；C 加防退化；D 两者启用。每组同一模型、初始候选、配置，最多一次真实请求。A/C 初始提示相同，B/D 初始提示相同；搜索证据仅 B/D 可见。所有组冻结后才执行共同历史审计和新的独立测试。','',
        '| 组 | 接受修改/保持 | 历史检出丢失 | 历史触发减少 | 历史新误报 | 搜索漏报剩余 | 独立漏报 | 独立误报 | 独立 unknown |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for n,r in records.items():
        h=r['historical_preservation'];t=r['independent']['counts']
        lines.append(f"| {n} | {r['decision']['accepted']} | {len(h['lost_original_detections'])} | {len(h['lost_original_triggers'])} | {len(h['new_original_false_positives'])} | {len(h['remaining_search_misses'])} | {t['misses']} | {t['false_positives']} | {t['unknown']} |")
    lines+=['',f"各组独立计数完全相同：{same_independent}；历史保护审计结果完全相同：{same_preservation}。",
        '若结果相同，本试验未证明搜索或门控带来额外收益；不得把所有组都能修复解释为两个机制独有成功。',
        f"相同初始提示的模型输出是否相同：`{result['same_prompt_output_equality']}`。请求中的 model、temperature 和 seed 相同不保证服务输出确定；单次输出差异不能替代多次随机重复。",
        f"隔离及完整性核验：`{checks}`。",
        f"本运行实际成本：`{cost['total']}`。准备阶段和源搜索的物理成本另行保存；B/D 共享采集但各自记逻辑64次执行，不能算免费。各组实际 token 和回放成本可能不同，详见 cost.json。",
        f"新的共同独立批次：seed {split['seed']}，{len(split['cases'])} 场景。",
        '完整模型原文、每组修改、决定、历史丢失/误报/触发明细见 results.json 和各组原生日志。单模型种子、单已知人工故障任务，不是多种子稳定性或真实历史父案例证明。','']
    for label,value in contrasts.items():
        lines.append(f"{label}（{value['treatment']}−{value['control']}）：独立结果差值 `{value['independent_delta']}`；历史检出丢失差值 {value['lost_historical_detections_delta']}。")
    for name,r in records.items():
        lines += [f"组 {name}：模型接口状态 `{r['model_call_result'].get('candidate_status')}`，"
                  f"接口原因 `{r['model_call_result'].get('candidate_error')}`。"]
        for change in r['changed_properties']:
            lines += [f"实际接受的 {change['id']}：", '```systemverilog',change['after'],'```']
        applicability=r.get('gate_trigger_rejection_applicability',[])
        if applicability:
            lines.append(f"门控触发拒绝 {len(applicability)} 条，其中上一拍复位已取消义务、独立检查器没有相应检查的记录 "
                         f"{sum(x['status']=='not_required_previous_reset_cancelled_stall_obligation' for x in applicability)} 条。"
                         "这些拒绝不能计为保住了真实必须检查的事务；暴露了历史触发门控的过度保守风险。")
    lines+=['','接口拒绝不记为原生编译失败；只对成功进入原生编译的表达式报告工具语义支持。','']
    lines += [f"对实际 B 冻结候选作只读门控复算：`{result['counterfactual_gate_on_B']}`。"
              "该复算不改变任何组的决定或独立结果；用于区分模型输出差异与门控规则本身的影响，详见 counterfactual_gate_on_B.json。",'']
    (report/'SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    shutil.copy2(__file__,report/'report_source.py')
    hashes={p.relative_to(run).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    dump(report/'manifest.json',hashes)
    failed=[n for n,h in hashes.items() if hashlib.sha256((run/n).read_bytes()).hexdigest()!=h]
    dump(report/'verification.json',dict(passed=not failed and all(checks.values()),files=len(files),failures=failed,checks=checks))
    print(dict(checks=checks,independent_tie=same_independent,preservation_tie=same_preservation),flush=True)


if __name__=='__main__':main()
