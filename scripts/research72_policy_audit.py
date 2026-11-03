"""Read-only provenance, isolation, native-decision and holdout policy audit."""
import argparse
import json
import time
from pathlib import Path

import research72_policy as run
import research68_result_audit as raw
from research28_report import raw_response
from research35_campaign import join_results, metrics
from research29_drain import assess

b, read, dump = run.b, run.read, run.dump


def audit(prep, root, out):
    run.verify(prep); out.mkdir(parents=True, exist_ok=False)
    start=time.perf_counter(); checks=[]; native_count=0; calls=[]; arms={}; rounds=[]
    outcome=read(root/'outcome.json'); protocol=read(prep/'protocol.json')
    initial=read(run.P/'shared_initial.json'); history=read(run.P/'history_cases.json')
    binding=read(run.P/'history_binding.json'); historical=read(b.gate.portable(binding['path']))
    acquired=[c for s in b.SEEDS for c in read(run.P/'ready'/f's{s}'/'search_cases.json')]
    def check(name, value):
        assert value, name
        checks.append(name)
    def replay(loc, cases, candidate):
        nonlocal native_count
        native_count+=raw.raw_replay(loc,cases,candidate,checks)
        return read(loc/'result.json')
    interrupted=False
    with b.extension.installed():
        for seed in b.SEEDS:
            ready=run.P/'ready'/f's{seed}'
            for name, spec in run.ARMS.items():
                key=f's{seed}/{name}'; loc=root/'arms'/key
                if not (loc/'initial_state.json').exists():continue
                check(key+' no arm after transport termination',not interrupted)
                stream='search' if spec['search'] else 'ordinary'
                source=read(prep/key/'request.preview.json'); request=source
                current=initial; past_edit=None; seen={b.interface.executable_hash(initial)}
                before=b.campaign.baseline(ready,stream); cases=read(ready/stream/'cases.json')
                decisions=[]; arm_calls=[]; interrupted_arm=False
                for iteration in range(run.ROUNDS):
                    folder=loc/'core'/f'v{iteration}'; model=folder/'model_call'
                    if not (model/'attempt.json').exists():break
                    tag=key+f'/v{iteration}'
                    check(tag+' no call after accepted version',not decisions or not decisions[-1]['accepted'])
                    call=read(model/'result.json'); calls.append(dict(arm=key,round=iteration,path=str(model),**call)); arm_calls.append(call)
                    check(tag+' exact permitted request',read(model/'request.json')==request)
                    check(tag+' no retries',call['retries']==0)
                    if iteration:
                        check(tag+' own preceding feedback persisted',request==read(loc/'core'/f'v{iteration-1}'/'next_request.preview.json'))
                    if call['status']!='response_received':
                        interrupted=True; interrupted_arm=True
                        check(tag+' transport no candidate',not (model/'candidate.json').exists())
                        check(tag+' transport retained current',read(folder/'active_candidate.json')==current)
                        check(tag+' no false terminal arm verdict',not (loc/'outcome.json').exists() and not (loc/'core/freeze.json').exists())
                        rounds.append(dict(arm=key,round=iteration,status=call['status'],accepted=None,transport_failure=True))
                        break
                    proposal=read(model/'candidate.json') if (model/'candidate.json').exists() else None
                    edit=read(model/'model_edit.json') if (model/'model_edit.json').exists() else None
                    if edit:check(tag+' raw response equals edit',raw_response(model,edit))
                    if proposal:check(tag+' syntax assembly no semantic rewriting',b.interface.assemble(edit,current)==proposal)
                    repeated=bool(proposal and edit['operation']!='keep' and b.interface.executable_hash(proposal) in seen)
                    if proposal:seen.add(b.interface.executable_hash(proposal))
                    small=full=None
                    if proposal and not repeated:
                        small=replay(folder/'visible_native',cases,proposal)
                    else:check(tag+' no invalid or repeated native compile',not (folder/'visible_native').exists())
                    plain=(b.paired.current_decision(before,small,edit) if small else
                           dict(accepted=False,reasons=[dict(kind='repeated_executable' if repeated else 'model_or_interface_failure')]))
                    check(tag+' ordinary decision recomputed',read(folder/'ordinary_decision.json')==plain)
                    if spec['gate'] and proposal and not repeated:
                        full=replay(folder/'history_native',history,proposal)
                        check(tag+' ordinary saved before history',(folder/'ordinary_decision.json').stat().st_mtime_ns < (folder/'history_native/result.json').stat().st_mtime_ns)
                    else:check(tag+' hidden history not read by ordinary arm',not (folder/'history_native').exists())
                    decision=run.decision_for(plain,full,historical,spec['gate'])
                    decision.update(call=call,repeated_executable=repeated,candidate_hash=b.loop.sha(proposal) if proposal else None,
                                    visible_counts=small['counts'] if small else None,history_counts=full['counts'] if full else None)
                    check(tag+' complete decision recomputed',decision==read(folder/'decision.json'))
                    previous=current; current=proposal if decision['accepted'] else current
                    check(tag+' active version actual accepted or retained',read(folder/'active_candidate.json')==current)
                    transition=read(folder/'active_transition.json')
                    check(tag+' durable transition hashes',transition['previous_hash']==b.loop.sha(previous) and
                          transition['active_hash']==b.loop.sha(current) and transition['retained_on_rejection']==(not decision['accepted']))
                    decisions.append(decision)
                    rounds.append(dict(arm=key,round=iteration,status=call['status'],accepted=decision['accepted'],
                        ordinary_accepted=plain['accepted'],gate_incremental_rejection=decision['gate_incremental_rejection'],
                        repeated=repeated,reasons=[r['kind'] for r in decision['reasons']],
                        visible=small['counts'] if small else None,history=full['counts'] if full else None,
                        proposal_hash=b.loop.sha(proposal) if proposal else None,
                        properties=proposal['assertions'] if proposal else None,
                        prompt_tokens=call.get('prompt_tokens'),completion_tokens=call.get('completion_tokens')))
                    if decision['accepted']:
                        check(tag+' accepted arm has no further request',not (folder/'next_request.preview.json').exists())
                        break
                    feedback=run.feedback_for(small,full,decision,call,edit,past_edit,spec['gate'])
                    check(tag+' actual feedback exact',feedback==read(folder/'next_feedback.json'))
                    check(tag+' historical feedback isolation',('historical_replay' in feedback)==(full is not None))
                    if iteration+1<run.ROUNDS:
                        request=b.campaign.request_from(source,current,seed,feedback)
                        check(tag+' next request from own current and diagnostics',request==read(folder/'next_request.preview.json'))
                    past_edit=edit
                check(key+' independent physical request cap',0<len(arm_calls)<=2)
                if interrupted_arm:
                    arms[key]=dict(completed=False,calls=len(arm_calls),search=spec['search'],gate=spec['gate'])
                    continue
                final=read(loc/'outcome.json')
                expected=dict(accepted=decisions[-1]['accepted'],frozen_hash=b.loop.sha(current),calls=len(arm_calls),
                    new_executable_version=b.interface.executable_hash(current)!=b.interface.executable_hash(initial),
                    search=spec['search'],gate=spec['gate'],rounds=decisions,
                    history_rejection_followed_by_acceptance=bool(decisions[-1]['accepted'] and any(d['gate_incremental_rejection'] for d in decisions[:-1])))
                check(key+' terminal summary recomputed',final==expected==outcome['decisions'][key])
                check(key+' frozen exact last active',read(loc/'core/frozen_candidate.json')==current and read(loc/'core/freeze.json')['candidate_sha256']==b.loop.sha(current))
                check(key+' stopped at acceptance or two calls',final['accepted'] or len(arm_calls)==2)
                arms[key]=dict(completed=True,accepted=final['accepted'],calls=len(arm_calls),frozen_hash=final['frozen_hash'],
                    search=spec['search'],gate=spec['gate'],history_rejection_followed_by_acceptance=final['history_rejection_followed_by_acceptance'])
                print('AUDITED_ARM',key,len(arm_calls),flush=True)
        check('actual distinct submissions capped',len(calls)==outcome['calls']<=24 and len({c['path'] for c in calls})==len(calls))
        check('completed arm denominator honest',sum(a['completed'] for a in arms.values())==outcome['completed_arms'])
        order=[k for k in protocol['order'] if k in arms]
        check('executed arms fixed prefix',order==protocol['order'][:len(order)])
        budget=read(root/'attempt_budget.json')
        check('actual call reservation accounting',budget['reserved']==len(calls)==outcome['reserved'])
        check('per-arm accounting',budget['per_arm']=={k:a['calls'] for k,a in arms.items()})
        if interrupted:
            check('transport terminal stops all',outcome['status'].startswith('terminal_') and calls[-1]['status']!='response_received')
            check('incomplete experiment has no independent tests',not (root/'evaluation').exists() and not (root/'all_arms_freeze.json').exists())
        evaluations={}
        if (root/'all_arms_freeze.json').exists():
            frozen=read(root/'all_arms_freeze.json');run.paired.barrier(frozen)
            check('all12 complete before measurement',set(arms)==run.KEYS and all(a['completed'] for a in arms.values()))
            common=read(root/'common_independent_split.json'); excluded=set(read(prep/'excluded_inputs.json')['input_hashes'])
            check('fresh independent input exclusion',not excluded&{b.loop.sha(c['rows']) for c in common['boundary_cases']+common['drain_cases']})
            for key, arm in arms.items():
                link=read(root/'arms'/key/'evaluation_binding.json');h=arm['frozen_hash'];dest=root/link['physical_evaluation']
                check(key+' measurement exact frozen candidate',link['candidate_hash']==h and b.loop.sha(read(dest/'core/frozen_candidate.json'))==h)
                if h not in evaluations:
                    candidate=read(dest/'core/frozen_candidate.json')
                    barrier_time=(root/'all_arms_freeze.json').stat().st_mtime_ns
                    check(h+' all terminal freezes before barrier',all((root/'arms'/k/'core/freeze.json').stat().st_mtime_ns <= barrier_time for k in arms))
                    check(h+' hidden final measurement after barrier',barrier_time < (dest/'history_native/result.json').stat().st_mtime_ns)
                    full=replay(dest/'history_native',history,candidate); targets=replay(dest/'search_native',acquired,candidate)
                    hg=b.gate.decide(historical['group']['ledger'],full['group']['ledger']) if full.get('group') else dict(accepted=False,reasons=[dict(kind='history_unavailable')])
                    measurement=dict(history_counts=full['counts'],search_counts=targets['counts'],history_gate=hg,
                        history_healthy=full['healthy'],search_healthy=targets['healthy'],no_feedback_no_selection=True)
                    check(h+' full final protection recomputed',measurement==read(dest/'measurement.json'))
                    split=read(dest/'independent/split.json')
                    check(h+' new test generation after barrier',barrier_time<(dest/'independent/split.json').stat().st_mtime_ns)
                    check(h+' exact candidate bound to test',split['frozen_hash']==h)
                    for field in ('seed','boundary_cases','drain_cases'):check(h+' common '+field,split[field]==common[field])
                    boundary=replay(dest/'independent/boundary',split['boundary_cases'],candidate)
                    drain=replay(dest/'independent/drain',split['drain_cases'],candidate)
                    combined=join_results([boundary,drain])
                    for row in combined['group']['ledger']:row['split']='independent_test'
                    m=metrics(combined);summary=read(dest/'independent/summary.json')
                    check(h+' independent metrics recomputed',m==summary['metrics'])
                    da=assess(dest/'independent/drain',split['drain_cases'],drain)
                    check(h+' drain actual exposure',da==read(dest/'independent/drain_assessment.json'))
                    passed=bool(combined['healthy'] and da['passed'] and all(v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown')) for v in m['obligations'].values()))
                    check(h+' independent all-five verdict',passed==summary['all_five_pass_on_first_attributed_evidence'])
                    evaluations[h]=dict(passed=passed,metrics=m,history_passed=bool(full['healthy'] and hg['accepted']),
                        history_counts=full['counts'],search_counts=targets['counts'],measurement_path=str(dest))
                    print('AUDITED_MEASUREMENT',h,flush=True)
                arm['measurement']=evaluations[h]
        else:check('no partial-group independent claim',not outcome['policy_effect_evaluated'])
    run.verify(prep)
    dump(out/'audit.json',dict(passed=True,checks=checks,native_records_recomputed=native_count,
        audit_wall_seconds=time.perf_counter()-start,model_calls=0,new_native_calls=0,
        source_sha256=b.search.digest(Path(__file__))))
    dump(out/'rounds.json',rounds);dump(out/'arms.json',arms)
    total={}
    for name in run.ARMS:
        selected=[a for k,a in arms.items() if k.endswith('/'+name)]
        total[name]=dict(planned=3,started=len(selected),completed=sum(a['completed'] for a in selected),
            accepted=sum(a.get('accepted',False) for a in selected),calls=sum(a['calls'] for a in selected),
            history_rejected_then_accepted=sum(a.get('history_rejection_followed_by_acceptance',False) for a in selected),
            tested=sum('measurement' in a for a in selected),history_passed=sum(a.get('measurement',{}).get('history_passed',False) for a in selected),
            independent_passed=sum(a.get('measurement',{}).get('passed',False) for a in selected))
    extra=sum(r.get('gate_incremental_rejection',False) for r in rounds)
    gate_ordinary=sum(r.get('ordinary_accepted',False) for r in rounds if r['arm'].endswith(('/C','/D')))
    results=dict(status=outcome['status'],arms=total,gate_incremental_rejections=extra,
        gated_proposals_ordinary_would_accept=gate_ordinary,physical_measurements=len(evaluations),
        policy_effect_evaluated=outcome['policy_effect_evaluated'])
    dump(out/'results.json',results)
    cost=read(root/'cost.json');by_arm={}
    for key,arm in arms.items():
        cs=[c for c in calls if c['arm']==key];cmds=[c for c in cost['native_commands'] if ('arms/'+key+'/') in c['path']]
        by_arm[key]=dict(model_calls=len(cs),prompt_tokens=sum(c['prompt_tokens'] for c in cs) if all(c.get('prompt_tokens') is not None for c in cs) else None,
            completion_tokens=sum(c['completion_tokens'] for c in cs) if all(c.get('completion_tokens') is not None for c in cs) else None,
            native_compile_calls=sum(c['kind']=='compile' for c in cmds),native_execute_calls=sum(c['kind']=='execute' for c in cmds))
    dump(out/'cost_by_arm.json',dict(arms=by_arm,total=cost['total'],monetary_cost=None,
        measurement='Final history/search/independent replays counted physically once per full candidate hash. Arm learning costs above exclude final measurements.',
        acquisition='research70 search and qualification actual cost retained separately; logically charged to search arms, not reexecuted.',
        reference_cost='Reference judgments are recomputed in native audit. Uninstrumented replay oracle time unavailable separately, not zero.'))
    report(out,prep,root,total,rounds,arms,extra,gate_ordinary,cost['total'],len(checks),native_count,results)
    print('AUDIT_POLICY',len(checks),'checks',native_count,'raw native records',flush=True)


def report(out,prep,root,total,rounds,arms,extra,denominator,cost,nchecks,native_count,results):
    lines=['# research72：独立多轮策略消融实跑结果','',f"终态：{results['status']}。实际调用{cost['model_calls']}/24；无自动重试。",'',
        '|组|完成/计划|接受|冻结后历史通过|新独立通过|实际调用|历史额外拒绝后再接受|','|---|---|---|---|---|---|---|']
    titles=dict(A='普通反馈',B='加搜索',C='加历史门控',D='两者启用')
    for name,v in total.items():
        t=v['tested'];hist=f"{v['history_passed']}/{t}" if t else '未执行';test=f"{v['independent_passed']}/{t}" if t else '未执行'
        lines.append(f"|{name} {titles[name]}|{v['completed']}/3|{v['accepted']}/{v['completed']}|{hist}|{test}|{v['calls']}|{v['history_rejected_then_accepted']}|")
    lines+=['','|轨迹|轮|本组接受|普通规则接受|历史额外拒绝|拒绝原因|','|---|---|---|---|---|---|']
    for r in rounds:lines.append(f"|{r['arm']}|{r['round']}|{r.get('accepted')}|{r.get('ordinary_accepted','未判定')}|{r.get('gate_incremental_rejection','未判定')}|{r.get('reasons',r['status'])}|")
    lines+=['',f'历史门控额外拒绝{extra}次；C/D中普通规则会接受的提案分母{denominator}。普通目标或接口已失败的提案，不计额外门控拒绝。',
        ('分母为0：没有合格提案进入额外拒绝判别，不能据此认定历史门控没有作用。' if denominator==0 else
         '额外拒绝仅按实际普通通过提案计数；这不是跨组共享响应的配对估计。'),
        '', '每条轨迹最多2次独立调用，接受即停，拒绝保留此前部分可用基线。A/C、B/D只共享首轮请求，未共享响应；没有使用research71提案或独立结果调参。C/D拒绝后的历史诊断只进入自己的下一轮。',
        '', '这是独立多轮策略实验，与共享提案的research71决定对照分开报告。各组不同响应受服务随机性影响；三个固定种子、单个FIFO与已知人工故障，不是多个历史Bug或全局效果证明。调用上限相同，实际调用、token与原生成本不必相同。',
        '', '未执行组保留分母；若传输中断，未冻结全部12组，不生成新独立测试，也不声称完成策略比较。',
        '',f"原始日志复核{native_count}份，{nchecks}项检查通过。实际成本：输入/输出tokens={cost['prompt_tokens_total']}/{cost['completion_tokens_total']}；用量不可用调用{cost['usage_unavailable_calls']}；编译{cost['native_compile_calls']}次、执行{cost['native_execute_calls']}次（含{cost['compile_smoke_execute_calls']}次启动自检），形式化{cost['formal_calls']}。",
        '', '成本细分见cost_by_arm.json与原始cost.json。既有搜索获取成本另见research70_audit_20261024_r01/cost_totals.json；货币费用与未单独计时的回放参考判定耗时不可用。',
        '', '新独立验收如已执行，只在所有轨迹冻结后生成。有限第一违例归因下的通过不代表全局保护；后续归因unknown继续保留。同哈希回放共享不是额外独立样本。分义务曝光、触发、检出、误报、漏报和unknown见arms.json。',
        '', '只读复核（新目录，无模型或仿真调用）：','```powershell',
        f'wsl -- python3 scripts/research72_policy_audit.py --prepared {prep.relative_to(run.ROOT).as_posix()} --run {root.relative_to(run.ROOT).as_posix()} --out deliverables/research72_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 真实修改与接受轨迹','', '展示首个种子6711的B/D两条实际轨迹，便于对照接受与拒绝后的行为。这是结果展示，不用于实验候选选择或修改统计分母；完整三种子见rounds.json及arms.json。',
           '', '公共初始性质：','```systemverilog']
    trace += [a['id']+': '+a['property'] for a in read(run.P/'shared_initial.json')['assertions']]
    trace+=['```']
    for key in ('s6711/B','s6711/D'):
        trace+=['',key]
        for r in rounds:
            if r['arm']!=key:continue
            trace+=['',f"轮{r['round']}：{r['status']}；接受={r['accepted']}。",'```systemverilog']
            trace += [a['id']+': '+a['property'] for a in r.get('properties') or []]
            trace+=['```',f"可见结果：{r.get('visible')}。",f"历史结果：{r.get('history')}。",f"拒绝原因：{r.get('reasons')}；历史额外拒绝={r.get('gate_incremental_rejection')}。"]
        a=arms.get(key)
        if a:
            trace+=['',f"最终状态：{ {k:v for k,v in a.items() if k!='measurement'} }"]
            if 'measurement' in a:trace += ['',f"冻结后测量：{a['measurement']}"]
        else:trace+=['未启动；不能计成功或失败。']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
