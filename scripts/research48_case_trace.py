"""Summarize actual failed SVA trajectories without changing experiment records."""
import json
from pathlib import Path
import research48_sva_campaign as c


def main():
    run=c.ROOT/'deliverables/research48_real_20261022_r01'
    out=c.ROOT/'deliverables/research48_report_20261022_r01'
    assert c.read(out/'audit.json')['passed']
    prep=c.gate.portable(c.read(run/'prepared_source.json')['path'])
    initial=c.read(prep/'shared_initial.json')
    targets=c.loop.inspect(c.read(prep/'core/initial_native/result.json')['group']['ledger'])['misses']
    traces=[]
    for version in ('v0','v2'):
        folder=run/'core'/version
        result=c.read(folder/'visible_native/result.json');info=c.loop.inspect(result['group']['ledger'])
        examples=[]
        for key in sorted(targets):
            row=info['rows'][key];path=c.gate.portable(row['source_directory'])/'replay.json'
            record=c.read(path)
            examples.append(dict(evidence_id=key,obligation=row['obligation'],cycle=row['cycle'],
                oracle=row['oracle'],native=row['native'],source=str(path),source_sha256=c.common.digest(path),
                samples=[{k:t.get(k) for k in ('cycle','rst','mvalid','mready','mdata')}
                         for t in record['trace'] if t['cycle'] in (row['cycle']-1,row['cycle'])]))
        traces.append(dict(version=version,property=c.read(folder/'model_call/candidate.json')['assertions'][4]['property'],
            rendered_edit=c.read(folder/'model_call/rendered_edit.json'),target_examples=examples,
            window_gate=c.read(folder/'native_window_gate.json'),
            current_counts=result['counts'],history_counts=c.read(folder/'history_native/result.json')['counts'],
            history_rejection_counts={r['kind']:len(r.get('evidence_keys',[])) for r in c.read(folder/'history_gate.json')['reasons']}))
    c.dump(out/'case_trace.json',dict(parent='axis_fifo_actual_RTL_with_artificial_boundary_faults',traces=traces))
    final=c.read(run/'core/v2/history_native/result.json')
    obligations={}
    for obligation in sorted({r['obligation'] for r in final['group']['ledger']}):
        parsed=c.loop.inspect([r for r in final['group']['ledger'] if r['obligation']==obligation])
        obligations[obligation]={k:len(parsed[k]) for k in ('rows','triggers','detections','misses','false_positives','unknown')}
    c.dump(out/'parent_result.json',dict(parent='axis_fifo',fault_provenance='explicit artificial boundary faults',
        accepted_new_set=False,whole_case_pass=False,new_independent_test=None,
        latest_rejected_candidate_history_by_obligation=obligations,
        later_attribution_unknown=final['counts']['later_attribution_unknown'],
        denominator='105 distinct historical scenarios per candidate; repeated candidate replays are not independent new scenarios.',
        historical_original_bug_reproduction=False))
    costs=[c.read(p/'cost.json')['total'] for p in (c.ROOT/'deliverables/research48_prepare_20261022_r01',prep,run)]
    totals={k:sum(v[k] for v in costs) for k in ('model_calls','native_compile_calls','native_execute_calls','compile_smoke_execute_calls','formal_calls')}
    c.dump(out/'all_stage_cost.json',dict(preparation_r01=costs[0],preparation_r02=costs[1],real_run=costs[2],physical_call_totals=totals,
        total_prompt_tokens=None,total_completion_tokens=None,reason='One HTTP400 call has unavailable usage; known subtotal54855 prompt/559 completion is not total usage.',monetary_cost=None))
    c.dump(out/'budget.json',dict(authorized_sva_calls=3,actual_http_attempts=3,decoded_proposals=2,
        service_http_error_calls=1,unused_sva_calls=0,retries=0,
        research47_transferred_remaining_call_consumed=True,
        research45_other4='Still restricted to the originally conditional ablation; not reused.'))
    lines=['# research48：计划正确后，性质仍未通过接受检查','',
        'research47实际模型计划在11个开发窗口上通过，但本轮SVA没有通过。三次真实请求中，两次产生可执行性质，一次HTTP400没有候选；失败调用用量不可用。',
        '','## 原性质与两次实际提案','',
        '原a4：','```sv',initial['assertions'][4]['property'],'```']
    for t in traces:
        lines+=['',t['version']+'实际模型性质：','```sv',t['property'],'```',
            '当前证据：'+json.dumps(t['current_counts'],ensure_ascii=False),
            '历史拒绝：'+json.dumps(t['history_rejection_counts'],ensure_ascii=False)]
        for e in t['target_examples']:
            lines+=['',f"实际目标cycle {e['cycle']}：",'```json',json.dumps(e['samples'],ensure_ascii=False,indent=2),'```']
    lines+=['','## 原生执行说明','',
        'v0继续在当前拍要求mvalid成立，并比较mdata与过去一拍；已接受输出切换新事务时出现误报，valid提前撤销时不能形成目标因果检出。当前16误报、2关键unknown，不能把misses=0写成补上漏报。',
        'v2新增过去一拍也背压的条件。当前误报降为0、unknown降为0，但两个原始目标仍漏报；native_target_gate记录这两个故障目标的a4均未触发。解除背压边界的合法配对也未触发。11个已通过模型适用性窗口中仍有4个必需窗口未被性质覆盖。',
        'v2在105场景历史中丢失31条原有检出和1048条触发证据，故防退化拒绝。该结论来自同一开发/历史证据回放，不是四组消融的机制收益估计。',
        '','## 保留状态和具体限制','',
        '最后保留原初始断言哈希0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1。没有新接受版本，也没有新独立测试。research46/47结果和旧冻结版本不变。',
        '每个提案的当前后续归因unknown95、历史后续归因unknown1177均保留；它们不是通过数。各义务分项见parent_result.json，完整映射在运行目录core/v*/obligation_mapping.json。',
        '第二次HTTP400的具体服务端原因不可用，不能确定为上下文长度、接口语法或其他原因。该调用不会冒充原生失败或已知零成本。',
        '事后发现无候选服务错误覆盖了最近详细原生诊断。未来版本已增加显式保留最近原生反馈的逻辑；本次原请求和结果不追改，新逻辑仅做本地记录验证，未追加真实调用。',
        '','## 实际运行命令','',
        '以下是已执行记录，目录不可覆盖，旧授权不可重复消耗；实际源码在运行目录source_snapshot中。','```powershell',
        'wsl -- python3 scripts/research48_sva_campaign.py run --prepared deliverables/research48_prepare_20261022_r02 --out deliverables/research48_real_20261022_r01 --authorization deliverables/research48_authorization_20261022_r01.json','```',
        '','后续需要重新准备采用保留原生反馈逻辑的请求，并明确新的SVA额度。本轮3次已耗尽，不能用原条件性消融额度继续。']
    (out/'CASE_TRACE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('CASE_TRACE_SAVED',totals,flush=True)


if __name__=='__main__':main()
