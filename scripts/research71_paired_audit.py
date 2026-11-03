"""Read-only audit of real paired proposals, native evidence and fresh tests."""
import argparse
from pathlib import Path
import research71_paired_run as run
import research68_result_audit as raw
from research28_report import raw_response
from research35_campaign import join_results,metrics
from research29_drain import assess

b,read,dump=run.b,run.read,run.dump


def audit(prep,root,out):
    run.verify(prep);out.mkdir(parents=True,exist_ok=False)
    outcome=read(root/'outcome.json');checks=[];native_count=0;details=[];arms={};calls=[]
    initial=read(run.P/'shared_initial.json');history=read(run.P/'history_cases.json')
    binding=read(run.P/'history_binding.json');historical=read(b.gate.portable(binding['path']))
    def check(name,value):assert value,name;checks.append(name)
    with b.extension.installed():
        for seed in b.SEEDS:
            ready=run.P/'ready'/f's{seed}'
            for stream,names in run.STREAMS:
                folder=root/'core'/f's{seed}'/stream;model=folder/'model_call'
                if not (model/'attempt.json').exists():continue
                label=f's{seed}/{stream}';calls.append(label)
                call=read(model/'result.json')
                usage={k:call.get(k) for k in ('prompt_tokens','completion_tokens','wall_seconds','usage_available')}
                check(label+' request exactly sealed',read(model/'request.json')==read(prep/f's{seed}'/stream/'request.preview.json'))
                check(label+' no transport retry',call['retries']==0)
                if call['status']!='response_received':
                    check(label+' transport failure has no proposal',not (model/'candidate.json').exists())
                    details.append(dict(seed=seed,stream=stream,status=call['status'],accepted=None,transport_failure=True,usage=usage))
                    continue
                proposal=read(model/'candidate.json') if (model/'candidate.json').exists() else None
                edit=read(model/'model_edit.json') if (model/'model_edit.json').exists() else None
                if edit:check(label+' edit equals raw upstream response',raw_response(model,edit))
                if proposal:check(label+' no semantic rewriting',b.interface.assemble(edit,initial)==proposal)
                repeated=bool(proposal and edit['operation']!='keep' and b.interface.executable_hash(proposal)==b.interface.executable_hash(initial))
                before=b.campaign.baseline(ready,stream);after=None;full=None
                if (folder/'visible_native/result.json').exists():
                    native_count+=raw.raw_replay(folder/'visible_native',read(ready/stream/'cases.json'),proposal,checks)
                    after=read(folder/'visible_native/result.json')
                plain=b.paired.current_decision(before,after,edit) if after else dict(accepted=False,reasons=[dict(kind='repeated_executable' if repeated else 'model_or_interface_failure')])
                check(label+' ordinary decision recomputed',plain==read(folder/'plain_decision.json'))
                if (folder/'history_native/result.json').exists():
                    check(label+' ordinary decided before history',
                        (folder/'plain_decision.json').stat().st_mtime_ns < (folder/'history_native/result.json').stat().st_mtime_ns)
                    native_count+=raw.raw_replay(folder/'history_native',history,proposal,checks)
                    full=read(folder/'history_native/result.json')
                hg=b.gate.decide(historical['group']['ledger'],full['group']['ledger']) if full and full.get('group') else dict(accepted=False,reasons=[dict(kind='history_native_unavailable')])
                check(label+' historical gate recomputed',hg==read(folder/'historical_gate.json'))
                gated=bool(plain['accepted'] and full and full['healthy'] and hg['accepted'])
                pair=read(folder/'pair_result.json')
                check(label+' ordinary and historical results',pair['plain']==plain and pair['gated']['accepted']==gated)
                reasons=plain['reasons']+hg['reasons']
                if full and not full['healthy']:reasons.append(dict(kind='history_native_or_legal_control_failure'))
                check(label+' rejection reasons recomputed',pair['gated']['reasons']==reasons)
                check(label+' paired counts match native records',pair['current_counts']==(after['counts'] if after else None) and pair['history_counts']==(full['counts'] if full else None))
                check(label+' incremental rejection not target failure',pair['gate_incremental_rejection']==bool(plain['accepted'] and not gated))
                for name,okay in zip(names,(plain['accepted'],gated)):
                    key=f's{seed}/{name}';loc=root/'arms'/key;candidate=proposal if okay else initial
                    check(key+' exact active and frozen candidate',read(loc/'active_candidate.json')==read(loc/'frozen_candidate.json')==candidate)
                    check(key+' hash bound',read(loc/'freeze.json')['candidate_sha256']==b.loop.sha(candidate))
                    transition=read(loc/'active_transition.json')
                    check(key+' rejected proposal retained baseline',transition['retained_on_rejection']==(not okay) and (okay or transition['previous_hash']==transition['active_hash']))
                    d=read(loc/'decision.json');check(key+' persisted decision matches outcome',d==outcome['decisions'][key] and d['accepted']==okay)
                    arms[key]=dict(accepted=okay,frozen_hash=b.loop.sha(candidate),stream=stream,gate=name==names[1])
                details.append(dict(seed=seed,stream=stream,status=call['status'],proposal_hash=b.loop.sha(proposal) if proposal else None,
                    usage=usage,
                    executable_hash=b.interface.executable_hash(proposal) if proposal else None,
                    properties=[dict(id=a['id'],property=a['property']) for a in proposal['assertions']] if proposal else None,
                    plain_accepted=plain['accepted'],gated_accepted=gated,
                    incremental_rejection=pair['gate_incremental_rejection'],reasons=[r['kind'] for r in pair['gated']['reasons']],
                    target_counts=after['counts'] if after else None,history_counts=full['counts'] if full else None))
        protocol=read(prep/'protocol.json')
        check('actual submitted calls exactly expected prefix',calls==protocol['call_order'][:len(calls)])
        check('six call cap',len(calls)==outcome['calls']<=6)
        if outcome['status'].startswith('terminal_'):
            check('transport stop is terminal last call',bool(details) and details[-1].get('transport_failure',False))
            check('incomplete arms did not enter tests',not (root/'common_independent_split.json').exists())
        evaluations={}
        if (root/'all_arms_freeze.json').exists():
            decisions=read(root/'all_arms_freeze.json');run.barrier(decisions)
            check('all12 actual decisions frozen',set(arms)==run.KEYS)
            common=read(root/'common_independent_split.json');inputs=common['boundary_cases']+common['drain_cases']
            check('independent inputs excluded all developer data',not set(read(prep/'excluded_inputs.json')['input_hashes'])&{b.loop.sha(c['rows']) for c in inputs})
            for key,d in arms.items():
                binding=read(root/'arms'/key/'evaluation_binding.json');h=d['frozen_hash'];dest=root/binding['physical_evaluation']
                check(key+' physical evaluation exact frozen hash',binding['candidate_hash']==h and b.loop.sha(read(dest/'core/frozen_candidate.json'))==h)
                if h not in evaluations:
                    split=read(dest/'independent/split.json');candidate=read(dest/'core/frozen_candidate.json')
                    check(h+' test split binds frozen candidate',split['frozen_hash']==h)
                    for field in ('seed','boundary_cases','drain_cases'):
                        check(h+field+' common test batch',split[field]==common[field])
                    check(h+' tests follow all-arm freeze',all((root/'arms'/k/'freeze.json').stat().st_mtime_ns<(dest/'independent/split.json').stat().st_mtime_ns for k in arms))
                    check(h+' complete freeze barrier precedes tests',(root/'all_arms_freeze.json').stat().st_mtime_ns<(dest/'independent/split.json').stat().st_mtime_ns)
                    for group,field in (('boundary','boundary_cases'),('drain','drain_cases')):
                        native_count+=raw.raw_replay(dest/'independent'/group,split[field],candidate,checks)
                    boundary=read(dest/'independent/boundary/result.json');drain=read(dest/'independent/drain/result.json')
                    combined=join_results([boundary,drain])
                    for row in combined['group']['ledger']:row['split']='independent_test'
                    m=metrics(combined);summary=read(dest/'independent/summary.json')
                    check(h+' independent metrics recomputed',m==summary['metrics'])
                    drain_check=assess(dest/'independent/drain',split['drain_cases'],drain)
                    check(h+' drain exposure recomputed',drain_check==read(dest/'independent/drain_assessment.json'))
                    passed=combined['healthy'] and drain_check['passed'] and all(v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown')) for v in m['obligations'].values())
                    check(h+' independent verdict recomputed',passed==summary['all_five_pass_on_first_attributed_evidence'])
                    evaluations[h]=dict(passed=passed,metrics=m,path=str(dest))
                d['independent']=evaluations[h]
        else:check('no uncommitted independent evaluation',not (root/'evaluation').exists())
    run.verify(prep)
    dump(out/'audit.json',dict(passed=True,checks=checks,native_records_recomputed=native_count,model_calls=0,new_native_calls=0,
        source_sha256=b.search.digest(Path(__file__))))
    dump(out/'proposals.json',details);dump(out/'arms.json',arms)
    totals={a:dict(accepted=sum(v['accepted'] for k,v in arms.items() if k.endswith('/'+a)),
        independent_passed=sum(v.get('independent',{}).get('passed',False) for k,v in arms.items() if k.endswith('/'+a)),
        independent_executed=sum('independent' in v for k,v in arms.items() if k.endswith('/'+a)),
        executed=sum(k.endswith('/'+a) for k in arms),planned=3) for a in 'ABCD'}
    increments=[d for d in details if d.get('incremental_rejection')]
    dump(out/'results.json',dict(outcome=outcome['status'],calls=len(calls),arms=totals,incremental_gate_rejections=len(increments),
        ordinary_accepted_proposals=sum(d.get('plain_accepted',False) for d in details),
        unique_physical_test_sets=len(evaluations),policy_effect_evaluated=False))
    raw_cost=read(root/'cost.json');cost=raw_cost['total'];by_stream={}
    for stream,_ in run.STREAMS:
        dd=[d for d in details if d['stream']==stream]
        commands=[c for c in raw_cost['native_commands'] if '/'+stream+'/' in c['path']]
        phase_cost={phase:dict(compile_calls=sum(c['kind']=='compile' and '/'+phase+'/' in c['path'] for c in commands),
            execute_calls=sum(c['kind']=='execute' and '/'+phase+'/' in c['path'] for c in commands))
            for phase in ('visible_native','history_native')}
        by_stream[stream]=dict(physical_model_calls=len(dd),logical_shared_call_allocations=2*len(dd),
            prompt_tokens=sum(d['usage']['prompt_tokens'] for d in dd) if all(d['usage']['prompt_tokens'] is not None for d in dd) else None,
            completion_tokens=sum(d['usage']['completion_tokens'] for d in dd) if all(d['usage']['completion_tokens'] is not None for d in dd) else None,
            compile_calls=sum(c['kind']=='compile' for c in commands),execute_calls=sum(c['kind']=='execute' for c in commands),
            replay_phases=phase_cost,
            logical_cost_allocation='A/B consume visible admission only; C/D additionally consume history. Shared proposal costs counted once physically, once per arm logically.',
            scope='Visible and history replay physical costs; independent evaluation, search acquisition and audit separate.')
    dump(out/'cost_by_stream.json',dict(streams=by_stream,total=cost,monetary_cost=None,
        search_acquisition='research70_audit_20261024_r01/cost_totals.json; physically once, logically B/D',
        reference_timing='Uninstrumented native replay oracle time unavailable separately; raw audit counts recorded, not zero-cost.'))
    lines=['# research71：三种子单轮配对消融','',f"终态：{outcome['status']}；实际模型调用{len(calls)}/6，无重试。",'',
        '|组|处理|接受/已执行决定|独立通过/已执行测试|计划种子|','|---|---|---|---|---|']
    titles=dict(A='普通反馈',B='加契约搜索',C='加历史门控',D='搜索＋历史门控')
    for name,v in totals.items():
        independent=f"{v['independent_passed']}/{v['independent_executed']}" if v['independent_executed'] else '未执行'
        lines.append(f"|{name}|{titles[name]}|{v['accepted']}/{v['executed']}|{independent}|3|")
    lines+=['','|种子|提案流|普通接受|加历史接受|额外拒绝|','|---|---|---|---|---|']
    for d in details:lines.append(f"|{d['seed']}|{d['stream']}|{d.get('plain_accepted','未判定')}|{d.get('gated_accepted','未判定')}|{d.get('incremental_rejection','未判定')}|")
    if evaluations:
        lines += ['','|物理冻结集合（哈希前12位）|绑定组|独立通过|检出|漏报|误报|关键unknown|后续归因unknown|',
                  '|---|---|---|---|---|---|---|---|']
        for h,v in evaluations.items():
            c=v['metrics']['counts'];keys=','.join(k for k,a in arms.items() if a['frozen_hash']==h)
            lines.append(f"|{h[:12]}|{keys}|{v['passed']}|{c['detections']}|{c['misses']}|{c['false_positives']}|{c['unknown']}|{c['later_attribution_unknown']}|")
        lines += ['', '此表按实际物理回放集合列出，不将共享组重复计为独立测试样本；完整分义务曝光、触发和保护映射见arms.json及原始回放目录。']
    lines+=['',f"历史门控额外拒绝{len(increments)}次，普通接受的真实提案分母为{sum(d.get('plain_accepted',False) for d in details)}。当前目标失败、接口失败或传输失败不计防退化增量作用。具体理由与实际保护ID保存在每对historical_gate.json。",
        '',f"原生日志复算{native_count}份，{len(checks)}项检查通过。物理独立回放{len(evaluations)}个不同候选集合；同哈希组共享实际回放，不能当作独立统计样本。所有已执行组的输入、输出、拒绝和基线保留记录均保留。",
        '',f"实际成本：模型{cost['model_calls']}次，tokens输入/输出={cost['prompt_tokens_total']}/{cost['completion_tokens_total']}，用量缺失{cost['usage_unavailable_calls']}次；原生编译{cost['native_compile_calls']}次、执行{cost['native_execute_calls']}次（含启动自检），形式化0。搜索获取和资格成本另见research70，原生日志审计重算成本不算新查询。",
        '',f"普通/搜索提案流实际成本分别为：{by_stream}。金额与原生回放内未单独计时的参考判定耗时保持不可用。",
        '', '本实验只估计同一真实提案的配对接受决定效果；不是各组独立多轮细化策略效果。A/C和B/D各共享一个真实响应；不同提案流不能被当成共享响应，服务seed的确定性未经证实。样本为单个FIFO父案例及已知人工故障，不是多个真实历史Bug。',
        '', '拒绝后保留公共初始集合。它通过105历史场景资格检查，但仍有已曝光valid漏报，因此是部分可用的基线，不是此前已经完整保护五义务的接受版本；不能把回退本身说成新目标已经修复。',
        '', '未见优势、失败和后续归因unknown均保留。独立通过限于预定第一违例归因范围，不是全局保护或形式化证明。不得用这批独立结果修改候选而继续称其独立。未启动或授权额外24次多轮策略实验。',
        '', '只读复核（新目录）：','```powershell',f'wsl -- python3 scripts/research71_paired_audit.py --prepared {prep.relative_to(run.ROOT).as_posix()} --run {root.relative_to(run.ROOT).as_posix()} --out deliverables/research71_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    traces=['# 实际配对轨迹','',
        '固定展示第一个种子6711的普通与搜索提案，不根据成功或收益筛选案例。完整结果见proposals.json与arms.json。',
        '', '初始性质（所有组相同）：','```systemverilog']
    traces += [a['id']+': '+a['property'] for a in initial['assertions']]
    traces += ['```']
    for d in details:
        if d['seed']!=b.SEEDS[0]:continue
        traces += ['', '提案流：'+d['stream'], '']
        if d.get('transport_failure'):
            traces += ['传输终态：'+d['status']+'；无新性质、无接受或独立结论。'];continue
        traces += ['模型实际性质：','```systemverilog']
        traces += [a['id']+': '+a['property'] for a in (d['properties'] or [])]
        traces += ['```','',f"可见证据结果：{d['target_counts']}",
                   '',f"105历史结果：{d['history_counts']}",
                   '',f"普通接受={d['plain_accepted']}；加历史接受={d['gated_accepted']}；额外拒绝={d['incremental_rejection']}。拒绝理由={d['reasons']}。"]
        for name in ('A','C') if d['stream']=='ordinary' else ('B','D'):
            key=f's{d["seed"]}/{name}';item=arms[key]
            independent=item.get('independent')
            traces += ['',f"{key} 冻结哈希 {item['frozen_hash']}；独立验收="+
                       (str(independent['passed'])+'，实际指标 '+str(independent['metrics']['counts']) if independent else '未执行')]
    traces += ['', '公共解除边界漏报在A/B/C/D都可见；持续背压漏报只作为B/D搜索处理的开发证据。普通提案若也补上相同保护，须保留该负收益结果。',
        '', '后续没有第二轮模型细化；本轮只测共享真实提案的门控决定。未拒绝提案不能声称门控额外保住历史保护；拒绝当前目标未修复的提案也不算防退化增量。',
        '', '同一候选在多组共享独立回放不增加样本数。完整哈希可能因解释元数据不同而不同，另记录executable_hash供语义结构重复核查；哈希相异本身不是新行为或新Bug。']
    (out/'CASE_TRACE.md').write_text('\n'.join(traces)+'\n',encoding='utf-8')
    print('AUDIT',len(checks),'checks',native_count,'native records',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
