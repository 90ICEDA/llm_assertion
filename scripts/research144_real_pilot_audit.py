"""Read-only audit of research142's real ordinary-rejection pilot result."""
import argparse
import json
from pathlib import Path
import research142_mapped_history_pilot as c

read,dump,digest,rel=c.read,c.dump,c.digest,c.rel


def audit(prep,run,out):
    opened=c.p.q.guard();c.verify(prep)
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):
        assert ok,name
        checks.append(name)
    unchanged={rel(f):digest(f) for f in run.rglob('*') if f.is_file() and 'obj_dir' not in f.parts}
    c.validate_grant(prep,run,read(run/'authorization.json'));checks.append('purpose_seal_output_grant')
    outcome=read(run/'outcome.json');call_dir=run/'shared/v0/model_call'
    call=read(call_dir/'result.json');edit=read(call_dir/'model_edit.json');candidate=read(call_dir/'candidate.json')
    assembled=read(call_dir/'response.assembled.json')
    check('real_completed_response',call['status']=='response_received' and call['stream_terminal_received'] and call['retries']==0)
    check('model_parameters',call['model']==call['actual_server_model']==c.p.s.MODEL)
    check('exact_response_to_edit',json.loads(assembled['message']['content'])==edit)
    initial=read(prep/'initial.json');baseline=read(prep/'baseline_full.json')
    check('verbatim_assembly',c.mapping.adapt(edit,initial)==candidate)
    check('model_picked_OP_first',candidate['assertions'][0]['obligations']==[c.mapping.OP])
    check('no_repeat',c.x.signature(candidate)!=c.x.signature(initial))
    records={k:read(c.BASE_NATIVE/k/'result.json') for k in ('alignment','search','history')}
    req=read(call_dir/'request.json')
    check('exact_sealed_and_executable_request',req==read(prep/'request.preview.json')==c.request(initial,records,c.BASE_NATIVE,False,0))
    check('public_only_request',set(json.loads(req['messages'][1]['content'])['actual_feedback']['visible_counts'])=={'alignment','search'})
    n,ev,replayed=c.mapping.inspect_version(run/'shared/v0/native',candidate,baseline)
    checks.append('raw_native_recomputed_'+str(n))
    check('both_rules_reject',not ev['ordinary']['accepted'] and not ev['full_absolute'])
    check('not_extra_historical_rejection',not ev['incremental_rejection'])
    expected=c.p.branch(call['status'],True,ev['ordinary']['accepted'],ev['full_absolute'],
                        len(ev['lost_detection_ids']),len(ev['new_false_alarm_ids']),c.critical_unknown(ev))
    check('correct_stop',expected==outcome['status']=='stop_ordinary_rejects' and outcome['completed'])
    check('first_decisions',outcome['first']==dict(O=False,H=False,branch=expected,measured=True))
    check('one_attempt',len(list(run.rglob('attempt.json')))==outcome['actual_model_calls']==1)
    check('no_second_attempt',not (run/'history').exists())
    check('not_recovery_population',not outcome['recovery_rate_estimable'] and not outcome['recovered_full151'])
    check('no_independent',not outcome['new_independent_executed'] and outcome['independent'] is None
          and not (run/'terminal_freeze.json').exists() and not (run/'independent_cases.json').exists())
    for arm in ('O','H'):
        f=run/'arms'/arm/'v0';tr=read(f/'transition.json')
        check(arm+'/baseline_retained',read(f/'active.json')==read(f/'before.json')==initial)
        check(arm+'/proposal_preserved',read(f/'proposal.json')==candidate)
        check(arm+'/hash_transition',not tr['accepted'] and tr['rollback_verified'] and
              tr['active_sha256']==tr['previous_sha256']==c.x.old.acceptance.sha(initial) and
              tr['proposal_sha256']==c.x.old.acceptance.sha(candidate))
    budget=c.Budget();budget.reserve('shared/v0',req);budget.reserve_native('shared/v0')
    saved=read(run/'budget_ledger.json');native=read(run/'native_reservations.json')
    strip=lambda xs:[{k:v for k,v in e.items() if k!='reserved_at'} for e in xs]
    check('budget_recomputed',strip(saved)==strip(budget.entries) and strip(native)==strip(budget.native))
    compiles=list(run.rglob('compile.json'));executions=list(run.rglob('execute.json'))
    check('six_physical_compiles_and_executions',len(compiles)==len(executions)==6)
    for f in compiles+executions:check('command/'+rel(f),read(f)['exit_code']==0)
    check('cost_recomputed',read(run/'cost.json')==c.physical_cost(run))
    check('usage_verified',call['prompt_tokens']==assembled['service_done']['usage']['prompt_tokens']
          and call['completion_tokens']==assembled['service_done']['usage']['completion_tokens'])
    summary={}
    full=c.x.paired.aggregate(replayed['history'],replayed['search']);info=c.x.old.acceptance.inspect(full['ledger'])
    for ob in (c.mapping.OP,c.mapping.BRANCH):
        summary[ob]={}
        for label,predicate in [('first',lambda r:r['sample']['phase']==0),('held',lambda r:r['sample']['phase']>0)]:
            keys={k for k,r in info['rows'].items() if r['obligation']==ob and predicate(r) and
                  r['revision']=='before' and r['oracle']['verdict']=='violated'}
            summary[ob][label]=dict(exposed=len(keys),detected=len(keys & info['detections']),
                                   missed=len(keys & info['misses']),unknown=len(keys & info['unknown']))
    focus=ev['current_gate']['focus12']
    check('focus_actual_6of12',focus['phases']['first']['detected']==3 and focus['phases']['held']['detected']==3
          and not focus['accepted'])
    # One continuous real instruction window, traced at every relevant phase.
    small=replayed['alignment'];config=c.x.old.CONFIGS[0]
    target=c.read(c.x.P/'focus.private.json')['targets'][0]['sample']['transaction_id']
    rows=[r for r in small['ledger'] if r['revision']=='before' and r['configuration']==config
          and r['sample']['transaction_id']==target]
    example=[]
    for row in rows:
        s=row['sample'];after=next(r for r in small['ledger'] if r['sample']==s and r['configuration']==config and r['revision']=='after')
        previous=[r for r in small['reference'] if r['sample_id']==s['sample_id']-1 and r['configuration']==config]
        example.append(dict(sample_id=s['sample_id'],transaction=s['transaction_id'],phase=s['phase'],
            instruction_hex=f"0x{s['instruction']:08x}",instr_new=s['instr_new'],previous_instr_new=previous[0]['instr_new'] if previous else None,
            expected=row['expected'],before=row['observed'],after=after['observed'],
            assertions=row['native']['assertions'],evidence_id=row['evidence_id']))
    check('held2_3_native_untriggered',all(not any(a['trigger'] or a['causal_detection'] for a in e['assertions'])
          and e['previous_instr_new']==0 and e['before']==0 and e['after']==e['expected']==1 for e in example if e['phase']>=2)
          and len([e for e in example if e['phase']>=2])==2)
    old_info=c.x.old.acceptance.inspect(baseline['ledger'])
    check('retained_baseline_partial270',len(old_info['detections'])==270 and len(old_info['misses'])==420)
    result=dict(passed=True,checks=len(checks),native_rows_recomputed=n,real_calls=1,authorized_maximum=2,
        new_accepted_versions=0,full151_replayed=True,current9_replayed=True,
        historical_detections=len(info['detections']),historical_misses=len(info['misses']),
        false_positives=len(info['false_positives']),critical_unknown=c.critical_unknown(ev),
        focus_detected=6,focus_exposed=12,proposal_lost_baseline_detections=len(ev['lost_detection_ids']),
        extra_historical_rejections=0,recovery_attempts=0,recovery_rate=None,independent_tests=0,
        baseline_retained_detections=270,per_obligation_phase=summary,
        tokens=dict(input=call['prompt_tokens'],output=call['completion_tokens']),native_compiles=6,native_executions=6,
        formal_calls=0,research133_read=False,stop_reason=expected)
    dump(out/'audit.json',result);dump(out/'checks.json',checks);dump(out/'phase_evidence.json',example)
    dump(out/'read_audit.json',sorted(opened))
    lines=['# research142 真实前瞻先导：普通检查已拒绝，按协议停止','',
        '新映射接收了模型生成的4条性质，OP置前、BRANCH置后，没有接口拒绝。原始模型表达式与时序未修改，原始Ibex decoder前后RTL均成功原生编译执行。',
        '模型的保持前件使用 !instr_new && $past(instr_new)，只覆盖从首周期进入的第一个保持周期。后续保持周期前一拍instr_new已为0，因此必要前件不触发。模型理由称非重叠检查，但实际输出timing均为same_sample；报告以实际可执行输出和原生记录为准。','',
        f"当前重点OP 12点：首周期3/3，保持3/9，总6/12；完整151事务检出{len(info['detections'])}/690，漏报{len(info['misses'])}，合法误报{len(info['false_positives'])}，关键unknown {c.critical_unknown(ev)}。下表只统计真实违例曝光；BRANCH首周期原始RTL正确，不要求虚构首周期违例。",'',
        '|义务|阶段|违例曝光|检出|漏报|unknown|','|---|---|---:|---:|---:|---:|']
    for ob,phases in summary.items():
        for phase,v in phases.items():lines.append(f"|{ob}|{phase}|{v['exposed']}|{v['detected']}|{v['missed']}|{v['unknown']}|")
    lines += ['',f"新提案丢失基线{len(ev['lost_detection_ids'])}个检出，但普通规则已经拒绝，历史规则不是额外拒绝的决定因素。两组实际活动版本仍为原270个BRANCH保护的部分基线，仍缺420个OP点；不能称完整案例通过。",'',
        '|里程碑|结果|','|---|---|','|真实调用|1/最多2|','|新接受版本|0|',
        '|原生回放|current9、search36、history115均执行|','|历史额外拒绝|0；普通已拒绝|',
        '|自动恢复|条件不成立，未调用；恢复率不可估计|','|新冻结/独立验收|未启动|','',
        '剩余一次额度仅限原协议的条件性历史反馈恢复。没有普通接受/历史额外拒绝的机会，因此停止，不作为通用提示修正额度，不扩种子。',
        f"实际成本：输入{call['prompt_tokens']}、输出{call['completion_tokens']} tokens，模型{call['wall_seconds']:.3f}秒；原生6次编译、6次实际执行、形式化0。执行与编译冒烟为同一路径，不重复计数；货币费用不可用。",'',
        f'审计复核{n}条原生记录、{len(checks)}项检查；请求等于封存版本，响应到可执行性质逐字段一致，预算、回退和停止分支均核验。research133未读取，旧研究结果不改。',
        '本轮确认新接口进入真实原生流程，但仍未取得前瞻性额外拒绝→恢复链，也没有新的搜索收益结论。若进一步研究，应另定协议，不自动追加同模型单字段修正。','',
        '只读复核（新输出目录，无模型或原生调用）：','```powershell',
        f'wsl -- python3 scripts/research144_real_pilot_audit.py --prepared {rel(prep)} --run {rel(run)} --out deliverables/research144_recheck','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 真实生成与原生失败轨迹','', '模型性质（原样）：','```systemverilog']
    trace += [a['property'] for a in candidate['assertions']]
    trace += ['```','', '|sample|phase|instr_new|前一拍instr_new|buggy/fixed/expected|触发ID|检出ID|', '|---|---:|---:|---:|---|---|---|']
    for e in example:
        trace.append(f"|{e['sample_id']}|{e['phase']}|{e['instr_new']}|{e['previous_instr_new']}|{e['before']}/{e['after']}/{e['expected']}|{[a['id'] for a in e['assertions'] if a['trigger']]}|{[a['id'] for a in e['assertions'] if a['causal_detection']]}|")
    trace += ['', '同一事务/指令、第一配置的实际采样。全部配置及断言标记保存在原生日志和phase_evidence.json，12点门控未通过。没有修改后SVA、恢复调用或独立测试，不能手工补成成功轨迹。']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    check('original_artifacts_unchanged',unchanged=={rel(f):digest(f) for f in run.rglob('*') if f.is_file() and 'obj_dir' not in f.parts})
    c.verify(prep)
    dump(out/'source_bindings.json',{**unchanged,rel(Path(__file__)):digest(Path(__file__)),rel(prep/'sealed.json'):digest(prep/'sealed.json')})
    # The final immutability check is recorded separately to keep report counts
    # equal to the decision checks already summarized above.
    dump(out/'immutability_check.json',dict(passed=True,original_file_count=len(unchanged)))
    dump(out/'sealed.json',{f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file()})
    print('AUDIT144',result,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('prepared','run','out'):ap.add_argument('--'+key,type=Path,required=True)
    a=ap.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
