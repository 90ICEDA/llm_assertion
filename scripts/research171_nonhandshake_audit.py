"""Read-only, retrospective transaction attribution of native KEEP alarms.

No model, simulator, candidate edit, gate patch, or acceptance decision is made.
Absence of a check is NOT evidence of correctness. Non-handshake alarms are
called early detections only with an uninterrupted, independently bad transfer.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
import research169_adapter_parameter_scope as s

q=s.q
PREP=q.ROOT/'deliverables/research169_scope_controller_prepare_20261028_r02'
RUN=q.ROOT/'deliverables/research169_adapter_run_20261028_r01'
PRIOR=q.ROOT/'deliverables/research170_adapter_real_report_20261028_r01'


def replay(trace):
    """Fixed registered 8->32 configuration. No SVA or failure list as input.

    Inspect pre-edge queue, retire on output acceptance, then append this edge's
    accepted input. Pending presented requests never enter the reference queue.
    """
    queue=[];active=None;prev=None;epoch=0;episodes=[];samples={};resets=[];accepted=[]
    illegal=set();issues=[];sid=None
    def close(status):
        nonlocal active
        if active is not None:
            active['status']=status;active=None
    for i,v in enumerate(trace):
        cycle=v['cycle']
        if i and cycle!=trace[i-1]['cycle']+1:issues.append(dict(cycle=cycle,reason='sample_gap'))
        if i==0 and (cycle!=0 or not v['rst']):issues.append(dict(cycle=cycle,reason='missing_initial_reset_context'))
        if sid!=v['sid']:
            close('scenario_boundary_without_transfer');queue=[];prev=None;epoch=0;sid=v['sid']
            if not v['rst']:issues.append(dict(cycle=cycle,reason='scenario_without_reset'))
        if v['rst']:
            resets.append(dict(cycle=cycle,sid=sid,cancelled_requests=copy.deepcopy(queue),
                cancelled_episode=active['id'] if active else None))
            close('reset_cancelled');queue=[];prev=None;epoch+=1
            samples[cycle]=dict(cycle=cycle,sid=sid,applicability='disabled_by_reset',episode=None)
            continue
        if prev and prev['sv'] and not prev['sr'] and (not v['sv'] or any(v[k]!=prev[k] for k in ('sd','sk','sl'))):illegal.add(sid)
        if active and prev and prev['mv'] and not prev['mr']:
            if not v['mv']:close('valid_withdrawn')
            elif any(v[k]!=prev[k] for k in ('md','mk','ml')):active['stable']=False
        row=dict(cycle=cycle,sid=sid,applicability='not_applicable_no_transfer',episode=None,
                 presented=bool(v['mv']),accepted_output=bool(v['mv'] and v['mr']))
        if v['mv']:
            end=next((j+1 for j,r in enumerate(queue[:4]) if r['last']),None)
            count=end if end is not None else min(4,len(queue))
            complete=bool(count and (end is not None or count==4))
            req=copy.deepcopy(queue[:count]);key=[r['id'] for r in req] if complete else None
            if active is None:
                active=dict(id=len(episodes),sid=sid,epoch=epoch,start_cycle=cycle,request_ids=key,
                    requests=req,stable=True,cycles=[],status='pending',transfer_cycle=None,
                    expected_keep=(1<<count)-1 if complete else None,expected_last=int(end is not None) if complete else None,
                    actual_first={k:v[k] for k in ('md','mk','ml')},alignment_known=complete)
                episodes.append(active)
            elif key!=active['request_ids']:active['alignment_known']=False
            active['cycles'].append(cycle);row['episode']=active['id']
            row['expected_keep']=(1<<count)-1 if complete else None
            row['request_ids']=key
            if v['mr']:
                row['applicability']='applicable_transfer' if complete else 'unknown_incomplete_reference'
                row['reference_checks']={} if not complete else dict(
                    keep_mask=v['mk']==(1<<count)-1,frame_boundary=v['ml']==int(end is not None),
                    byte_order=all(((v['md']>>(8*j))&255)==r['byte'] for j,r in enumerate(req)))
                active['transfer_cycle']=cycle;active['transfer_reference']=copy.deepcopy(row)
                close('accepted')
                if complete:queue=queue[count:]
                else:issues.append(dict(cycle=cycle,reason='cannot_align_output_transfer'))
        samples[cycle]=row
        if v['sv'] and v['sr']:
            r=dict(id=f'{sid}:{epoch}:{cycle}',cycle=cycle,sid=sid,epoch=epoch,byte=v['sd'],last=v['sl'])
            queue.append(r);accepted.append(r)
        prev=v
    close('trace_ended_without_transfer')
    return dict(samples=samples,episodes=episodes,accepted_inputs=accepted,reset_cancellations=resets,
        illegal_source_scenarios=sorted(illegal),trace_issues=issues,
        scope='registered upsize8to32 S_KEEP_ENABLE0 only; audit not a production acceptance oracle')


def classify(reference,cycle,label):
    r=dict(cycle=cycle,assertion=label,category='unknown',reason=None)
    sample=reference['samples'].get(cycle)
    if sample is None:r['reason']='missing_alarm_sample';return r
    r['reference_applicability']=sample['applicability'];r['sid']=sample['sid']
    if reference['trace_issues']:r['reason']='incomplete_or_unalignable_trace';return r
    if sample['sid'] in reference['illegal_source_scenarios']:r['reason']='illegal_source';return r
    if sample['episode'] is None:r['reason']='no_active_output_episode';return r
    e=reference['episodes'][sample['episode']];r['episode_id']=e['id'];r['request_ids']=e['request_ids']
    r['presentation_cycle']=e['start_cycle'];r['transfer_cycle']=e['transfer_cycle']
    if not e['alignment_known']:r['reason']='reference_group_unknown';return r
    if not all(x['cycle']<cycle for x in e['requests']):r['reason']='request_not_accepted_before_alarm';return r
    if e['status']!='accepted':r['reason']=e['status'];return r
    if not e['stable']:r['reason']='changed_payload_before_transfer';return r
    checks=e['transfer_reference']['reference_checks']
    if not checks:r['reason']='reference_verdict_missing';return r
    if not checks['keep_mask']:
        if cycle==e['transfer_cycle']:
            r.update(category='confirmed_target_detection',reason='independent_keep_violation_at_acceptance')
        else:r.update(category='confirmed_early_detection',reason='same_stable_output_later_violates_keep_at_acceptance')
    elif all(checks.values()) and cycle==e['transfer_cycle']:
        r.update(category='confirmed_false_positive',reason='fully_reference_valid_transfer_but_assertion_failed')
    else:r['reason']='nontransfer_applicability_or_other_obligation_unresolved'
    return r


def alarms(folder):
    n=q.read(folder/'result.json')
    assert n['compile_status']=='passed' and n['execution_status']=='completed'
    return [dict(cycle=int(re.fullmatch(r'cycle=(\d+)',f['detail'])[1]),label=f['id']) for f in n['failures']]


def main(out):
    s.c.verify(PREP);s.c.verify(s.OLD)
    for p,h in q.read(PRIOR/'seal.json').items():assert q.sha(PRIOR/p)==h,p
    for p,h in q.read(PRIOR/'source_bindings.json').items():assert q.sha(q.ROOT/p)==h,p
    checks,check=s.check_list();sources=[]
    def source(path):
        sources.append(path);return q.read(path)
    original_outcome=source(RUN/'outcome.json');old_ev=source(RUN/'shared/evaluation.json')
    initial_hash=q.sha(RUN/'terminal_versions.json');old_hash=q.sha(RUN/'outcome.json')
    datasets={};all_refs={}
    for name,folder in [('real_before',RUN/'shared/native/before'),('real_after',RUN/'shared/native/after'),
                        ('overbroad_before',s.c.N/'overbroad/before'),('overbroad_after',s.c.N/'overbroad/after')]:
        for f in ('result.json','execute.log','tb.sv','compile.json','execute.json'):sources.append(folder/f)
        trace=q.old.trace(folder);reference=replay(trace);old=q.adjudicate(trace);all_refs[name]=(trace,reference,old)
        check(name+' complete trace',len(trace)==33*96 and not reference['trace_issues'])
        check(name+' legal source',not reference['illegal_source_scenarios'] and old['legal'])
        for event in (e for e in old['events'] if e['kind']=='output'):
            row=reference['samples'][event['cycle']];episode=reference['episodes'][row['episode']]
            check(name+' independent request alignment '+str(event['cycle']),[r['cycle'] for r in episode['requests']]==[r['cycle'] for r in event['requests']])
            check(name+' expected keep agrees '+str(event['cycle']),row['expected_keep']==event['expected_keep'])
        entries=alarms(folder)
        rows=[classify(reference,e['cycle'],e['label']) for e in entries]
        datasets[name]=dict(rows=rows,counts=dict(Counter(r['category'] for r in rows)),
                           unique_cycle_counts=dict(Counter(k for k in set((r['category'],r['cycle']) for r in rows))))
        # JSON-friendly distinct cycle totals; labels can produce duplicate alarms.
        datasets[name]['unique_cycle_counts']={cat:len({r['cycle'] for r in rows if r['category']==cat}) for cat in {r['category'] for r in rows}}
    trace,ref,old=all_refs['real_before'];extra=set(old_ev['false_before'])
    extra_rows=[r for r in datasets['real_before']['rows'] if r['cycle'] in extra]
    check('68 exact original extra alarm records',len(extra_rows)==len(extra)==68)
    check('all68 early confirmed',all(r['category']=='confirmed_early_detection' for r in extra_rows))
    check('not applicable is never pass',all(r['reference_applicability']=='not_applicable_no_transfer' for r in extra_rows))
    check('no false alarms on repaired RTL',datasets['real_after']['rows']==[])
    control=datasets['overbroad_after']['rows']
    check('real legal overbroad control exposes false positives',len(control)>0 and all(r['category']=='confirmed_false_positive' for r in control))
    after_trace,after_ref,_=all_refs['overbroad_after']
    check('control partial final valid transfers',all(after_trace[r['cycle']]['ml']==1 and 0<after_trace[r['cycle']]['mk']<15 and after_trace[r['cycle']]['mv'] and after_trace[r['cycle']]['mr'] for r in control))
    # Counterfactual fixtures test ONLY the classifier. They are not native/model results.
    anchor=extra_rows[0]['cycle'];stop=extra_rows[0]['transfer_cycle'];label=extra_rows[0]['assertion']
    mutations=[]
    def unit(name,values,reason):
        r=classify(replay(values),anchor,label)
        check('synthetic control '+name,r['category']=='unknown' and r['reason']==reason)
        mutations.append(dict(name=name,origin='synthetic_python_classifier_control_not_native',result=r,
            trace_sha256=s.c.digest(values)))
    unit('truncate before actual transfer',copy.deepcopy(trace[:stop]),'trace_ended_without_transfer')
    v=copy.deepcopy(trace[:anchor+2]);v[-1]['rst']=1
    unit('reset before actual transfer',v,'reset_cancelled')
    v=copy.deepcopy(trace);v[anchor+1]['mv']=0
    unit('withdraw valid then re-present identical payload',v,'valid_withdrawn')
    v=copy.deepcopy(trace);v[anchor+1]['md']^=1
    unit('change payload then restore before target',v,'changed_payload_before_transfer')
    v=copy.deepcopy(trace);v.pop(anchor+1)
    unit('missing sample inside hold interval',v,'incomplete_or_unalignable_trace')
    v=copy.deepcopy(trace[:anchor+2]);v[-1]['sid']+=1;v[-1]['rst']=1
    unit('scenario boundary cannot reuse following target',v,'scenario_boundary_without_transfer')
    v=copy.deepcopy(trace)
    for r in ref['episodes'][extra_rows[0]['episode_id']]['requests']:v[r['cycle']]['sr']=0
    unit('request presented but never accepted',v,'incomplete_or_unalignable_trace')
    # A known native reset control: pending inputs cancel without inventing output transfers.
    cancelled=[x for x in ref['reset_cancellations'] if x['cancelled_requests']]
    check('actual native reset cancellation retained',bool(cancelled))
    check('cancelled input IDs never appear in later accepted output',all(not ({r['id'] for r in x['cancelled_requests']} & {rid for e in ref['episodes'] if e['status']=='accepted' and e['transfer_cycle']>x['cycle'] for rid in (e['request_ids'] or [])}) for x in cancelled))
    # Same payload does not merge two separately accepted source requests.
    repeated=[]
    for cycle in range(9):
        v=dict(trace[0]);v.update(cycle=cycle,phase=cycle,sid=0,rst=int(cycle<2),sv=int(cycle in (3,4)),sr=1,sd=7,sk=1,sl=1,
            mv=int(cycle in (4,5,6,7)),mr=int(cycle in (6,7)),md=7,mk=0,ml=1)
        repeated.append(v)
    rr=replay(repeated);er=[e for e in rr['episodes'] if e['status']=='accepted']
    check('same payload separate transaction IDs',len(er)==2 and er[0]['request_ids']!=er[1]['request_ids'])
    check('early alarm belongs only to first transaction',classify(rr,4,'synthetic')['transfer_cycle']==6)
    mutations.append(dict(name='same_payload_distinct_requests',origin='synthetic_python_classifier_control_not_native',episodes=er))
    # Every extra alarm's full reference chain, with old and new diagnostic labels kept separate.
    chains=[]
    fixed_trace,fixed_ref,_=all_refs['real_after']
    for r in extra_rows:
        episode=ref['episodes'][r['episode_id']];cycle=r['cycle'];end=r['transfer_cycle']
        check('strictly prior accepted input '+str(cycle),all(x['cycle']<cycle for x in episode['requests']))
        fixed_row=fixed_ref['samples'][end]
        check('fixed same input/output pairing '+str(cycle),fixed_row['request_ids']==episode['request_ids'])
        check('fixed reference satisfied at paired transfer '+str(cycle),all(fixed_row['reference_checks'].values()))
        chains.append(dict(**r,old_sealed_label='false_before',accepted_requests=episode['requests'],
            expected_keep=episode['expected_keep'],held_samples=trace[episode['start_cycle']:end+1],
            fixed_paired_sample=fixed_trace[end],fixed_reference=fixed_row,
            current_cycle_obligation='Accepted-output KEEP contract not applicable yet; no pass inferred.',
            retrospective_basis='Uninterrupted same output + accepted input reference + actual bad transfer; not a global presented-KEEP theorem.'))
    check('old outcome remains rejection',q.sha(RUN/'outcome.json')==old_hash and original_outcome['status']=='stop_ordinary_rejects')
    check('old active candidate unchanged',q.sha(RUN/'terminal_versions.json')==initial_hash)
    source_code=(q.ROOT/'scripts/research167_adapter_controller.py').read_text()
    check('frozen false-positive assumption located','false_before=failed-targets' in source_code)
    out.mkdir(parents=True,exist_ok=False)
    q.dump(out/'alarm_chains.json',chains);q.dump(out/'classifications.json',datasets)
    q.dump(out/'transaction_reference.json',{k:v[1] for k,v in all_refs.items()})
    q.dump(out/'synthetic_classifier_controls.json',mutations);q.dump(out/'checks.json',checks)
    episode_ids=sorted({r['episode_id'] for r in extra_rows});transfer_cycles=sorted({r['transfer_cycle'] for r in extra_rows})
    metrics=dict(real_extra_alarms=68,confirmed_early=68,confirmed_false_positive_in_these68=0,unknown_in_these68=0,
        distinct_output_transactions=len(episode_ids),distinct_existing_target_cycles=len(transfer_cycles),new_bug_discoveries=0,
        overbroad_control_counts={k:datasets[k]['counts'] for k in ('overbroad_before','overbroad_after')},
        conditional_recovery=dict(numerator=0,denominator=0,rate=None),new_acceptances=0,new_independent_tests=0,
        cost=dict(model_calls=0,native_compiles=0,native_executions=0,formal_calls=0,reused_native_records=4),
        old_verdict='stop_ordinary_rejects',production_gate_changed=False)
    q.dump(out/'metrics.json',metrics)
    q.dump(out/'audit_scope.json',dict(status='retrospective_development_audit_only_not_new_acceptance_protocol',
        fixed_config=s.PARAMETERS,assumptions=['registered upsize output uses earlier accepted bytes','source valid is not acceptance',
        'reset cancels unfinished requests','non-handshake KEEP has no verdict in frozen accepted-output contract',
        'only actual stable future handshake confirms early detection; no prediction across cancellation/truncation'],
        future_gate_requirements=['explicit applicability and pass/fail/unknown states','obligation-specific transaction alignment',
        'genuine false-positive native controls retained','unknown rejects; early detection deduplicated with target transaction',
        'validate and seal separately; never retroactively accept research169'],
        no_new_protocol_sealed=True))
    example=chains[0]
    (out/'SUMMARY.md').write_text(f'''# research171 非握手周期参考判定审计

完成只读开发记录审计。没有模型调用、原生重跑或独立测试；没有修改断言、research169门控或原拒绝决定。

| 对象 | 结果 |
| --- | --- |
| 原68个额外报警 | 68个确认提前检出；真正误报0；unknown0 |
| 去重后对应 | {len(episode_ids)}个已知错误输出事务、{len(transfer_cycles)}个既有目标握手周期；新增Bug0 |
| 修复后同输入记录 | 无断言报警；配对握手均通过独立参考检查 |
| 既有过宽断言对照（修复后RTL） | {len(control)}个真正误报，均为规格允许的合法部分尾拍 |
| 条件恢复 | 仍0/0，不可估计 |
| research169 | 仍为普通规则拒绝；旧基线保留；新接受0、独立验收0 |

## 核查到的判定缺陷

原参考模型只在valid&&ready时检查输出KEEP，非握手周期不存在该义务判定。旧门控却用`false_before = failed - targets`把“没有已记录违例”当成“已确认正确”，丢失了义务是否适用的信息。68个背压期间的报警因此被记入false_before。

新审计依据此前已握手输入重建字节队列，不把请求呈现当作接受，不用待评估SVA作正确性依据。输出呈现、保持、实际握手和复位取消分别记录；同值数据用输入接受事件ID区分。只有合法输入、完整记录、同一输出始终保持、没有复位取消、最终实际握手且独立KEEP参考判为违例，才分类为“确认提前检出”。

这里的“提前”是对完整已观察轨迹的事后归因，不表示原封存契约已经在非握手周期适用，也不证明任意配置都要求valid时KEEP非零。没有该周期检查不能记为pass；没有后续见证不能推断会违例。

## 一条可追溯实例

报警周期{example['cycle']}，输入接受周期{[x['cycle'] for x in example['accepted_requests']]}，输出从周期{example['presentation_cycle']}开始呈现；背压下保持至周期{example['transfer_cycle']}实际握手。独立期望KEEP={example['expected_keep']}，buggy输出KEEP=0；fixed配对输出KEEP={example['fixed_paired_sample']['mk']}。完整输入、保持样本及参考判定见alarm_chains.json，每个报警单独一行。

## 分类负对照及限制

复用了真实原生过宽断言记录：对合法部分尾拍强制满KEEP会被独立参考确认为真正误报，未被提前检出逻辑洗掉。Python分类器对照另验证复位取消、记录截断、valid撤回、载荷变化、采样缺失、场景切换和未接受请求均不能强行分类为提前检出。这些变造轨迹仅是明确标注的分类器测试，不算RTL实验或模型证据。实际原生日志中的复位取消也已核对不会借用之后事务。

{len(checks)}项审计检查通过。68个报警不新增68个有效缺口，也不能计防退化收益。H/R等价、576查询无独有收益及既有FIFO独立范围均不改变。

## 下一步边界

参考判定缺陷已有证据；若要用于后续接受检查，应另行实现显式适用性与三态判定，并验证义务对应、取消/截断unknown和真实误报对照，再封存新协议。本次只形成审计结论，不修改生产门控、不申请模型预算、不追改research169成功。

复核命令（读取相同原生记录，写入新目录）：
```powershell
wsl -- python3 scripts/research171_nonhandshake_audit.py --out deliverables/research171_nonhandshake_audit_repeat
```
''',encoding='utf-8')
    sources += [Path(__file__),PREP/'seal.json',PRIOR/'seal.json',q.ROOT/'scripts/research165_adapter_qualification.py',
        q.ROOT/'scripts/research167_adapter_controller.py',RUN/'terminal_versions.json']
    for rev in ('before','after'):sources.append(s.c.P/'rtl'/rev/'axis_adapter.v')
    q.dump(out/'source_bindings.json',{q.old.rel(p):q.sha(p) for p in sources});s.seal_files(out)
    s.c.verify(PREP)
    print(json.dumps(dict(checks=len(checks),metrics=metrics),ensure_ascii=False),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args();main(a.out.resolve())
