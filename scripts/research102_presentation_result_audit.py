"""Reconstruct the sealed research100 requests, native decisions and holdout."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research100_presentation_pilot as run100
from research93_remote_recovery_audit import response
from research88_cross_parent_audit import inspect_version

p,x,fmt=run100.p,run100.x,run100.fmt
ROOT,read,dump,sha=run100.ROOT,run100.read,run100.dump,run100.sha


def run(prep,trial,out):
    run100.verify(prep);run100.grant_check(read(trial/'authorization.json'),prep,trial)
    initial=read(prep/'initial.json');base=read(prep/'baseline_full.json')
    active={a:initial for a in run100.ARMS};current={a:initial for a in run100.ARMS}
    visible={a:read(prep/'initial_feedback.json') for a in run100.ARMS}
    records={a:run100.initial_records() for a in run100.ARMS}
    diagnostic={a:None for a in run100.ARMS};seen={a:{x.signature(initial)} for a in run100.ARMS}
    states={a:dict(accepted=False,calls=0) for a in run100.ARMS}
    ledger=read(trial/'budget_ledger.json');assert 1<=len(ledger)<=4
    versions=[];rows=0;calls=[];order=[];stopped=False
    per_arm={a:dict(calls=0,prompt_tokens=0,completion_tokens=0,usage_unavailable=0,model_wall_seconds=0,native_compile_execute=0) for a in run100.ARMS}
    for item in ledger:
        arm=item['arm'];iteration=item['iteration'];order.append(iteration*2+run100.ARMS.index(arm))
        assert not stopped and not states[arm]['accepted'] and iteration==states[arm]['calls']<2
        folder=trial/arm/f'v{iteration}';mf=folder/'model_call'
        req=read(mf/'request.json')
        assert req==fmt.request(current[arm],visible[arm],records[arm],arm,iteration,diagnostic[arm])
        if iteration==0:assert req==read(prep/arm/'request.preview.json')
        assert item['request_sha256']==x.old.acceptance.sha(req)
        reservation=sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']
        assert item['reservation']==reservation<=30000
        text,raw=response(mf);call=read(mf/'result.json');calls.append(call)
        t=read(folder/'transition/transition.json');candidate=None;ev=None
        status=t['reason']['kind'];accepted=False
        if (mf/'candidate.json').exists():
            edit=read(mf/'model_edit.json');assert json.loads(text)==edit
            candidate,_=p.prior.p.TEXT_ADAPT(edit,initial)
            assert candidate==read(mf/'candidate.json') and candidate['assertions'][0]==initial['assertions'][0]
            for rawprop,prop in zip(edit['assertions'],candidate['assertions'][1:]):
                assert all(rawprop[k]==prop[k] for k in fmt.FIELDS)
            if status=='repeated_executable_proposal':
                assert x.signature(candidate) in seen[arm] and not (folder/'native').exists();candidate=None
            else:
                assert status=='native_measured' and x.signature(candidate) not in seen[arm]
                seen[arm].add(x.signature(candidate))
                n,ev,rec=inspect_version(folder/'native',candidate,base);rows+=n
                assert t['reason']['decision']==ev
                accepted=bool(ev['history']['accepted'])
                current[arm]=candidate;records[arm]=rec;visible[arm]=p.feedback(ev,rec,True)
                per_arm[arm]['native_compile_execute']+=6
        else:assert status=='transport_or_interface'
        if ev is None:diagnostic[arm]=dict(reason=t['reason'],actual_model_text=text)
        else:diagnostic[arm]=None
        assert t['accepted']==accepted and t['previous_sha256']==x.old.acceptance.sha(active[arm])
        assert read(folder/'transition/before.json')==active[arm]
        if candidate is not None:assert read(folder/'transition/proposal.json')==candidate
        assert t['proposal_sha256']==(x.old.acceptance.sha(candidate) if candidate else None)
        expected=candidate if accepted else active[arm]
        assert read(folder/'transition/active.json')==expected
        assert t['active_sha256']==x.old.acceptance.sha(expected) and t['rollback_verified']
        active[arm]=expected;states[arm]['calls']+=1;states[arm]['accepted']=accepted
        stopped=call['status']!='response_received'
        c=per_arm[arm];c['calls']+=1;c['model_wall_seconds']+=call['wall_seconds']
        if call.get('prompt_tokens') is None or call.get('completion_tokens') is None:c['usage_unavailable']+=1
        else:c['prompt_tokens']+=call['prompt_tokens'];c['completion_tokens']+=call['completion_tokens']
        edit=read(mf/'model_edit.json') if (mf/'model_edit.json').exists() else None
        versions.append(dict(arm=arm,iteration=iteration,accepted=accepted,reason=status,
            interface_status=call.get('candidate_status'),interface_error=call.get('candidate_error'),
            raw_response=raw,edit=edit,counts=ev['counts'] if ev else None,
            focus12=ev['current_gate']['focus12'] if ev else None,
            decisions=p.decisions(ev) if ev else None,
            retained_detections=len(ev['retained_detection_ids']) if ev else None,
            lost_detections=len(ev['lost_detection_ids']) if ev else None,
            new_false_alarms=len(ev['new_false_alarm_ids']) if ev else None))
    assert order==sorted(set(order))
    assert read(trial/'states.json')==states
    outcome=read(trial/'outcome.json');cost=read(trial/'cost.json')['total']
    assert outcome['states']==states and outcome['actual_calls']==len(calls)==cost['model_calls']
    assert outcome['transport_stopped']==stopped and not outcome['automatic_expansion']
    assert cost['native_compile_calls']<=28 and cost['native_execute_calls']<=28
    charged=sum(c['prompt_tokens']+c['completion_tokens'] if c.get('prompt_tokens') is not None and c.get('completion_tokens') is not None else c['token_budget_reservation'] for c in calls)
    assert charged<=120000
    assert outcome['unique_new_accepted_versions']==len({x.old.acceptance.sha(active[a]) for a in run100.ARMS if states[a]['accepted']})
    assert read(trial/'terminal_versions.json')=={a:x.old.acceptance.sha(c) for a,c in active.items()}
    for a,c in active.items():assert read(trial/'terminal'/a/'candidate.json')==c
    tests=None
    if (trial/'independent_summary.json').exists():
        assert not stopped and any(s['accepted'] for s in states.values())
        tests=read(trial/'independent_summary.json');freeze=read(trial/'freeze.json')
        generation=read(trial/'generation.json');cases=read(trial/'independent_cases.json')
        assert generation['at']>freeze['time'] and generation['freeze_sha256']==sha(trial/'freeze.json')
        assert freeze['development_exclusion_sha256']==sha(prep/'excluded_words.json')
        assert freeze['source_sha256']==read(prep/'source_binding.json')['source_sha256']
        assert cases==x.holdout.base.generate(generation['seed'],read(prep/'excluded_words.json'))
        assert len({t['instruction'] for t in cases})==96
        assert not {t['instruction'] for t in cases}&set(read(prep/'excluded_words.json'))
        for arm,candidate in active.items():
            f=trial/'frozen'/arm;result=read(f/'independent/result.json')
            assert read(f/'candidate.json')==candidate and x.old.acceptance.sha(candidate)==freeze['versions'][arm]
            assert read(f/'independent_cases.json')==cases
            for rev in ('before','after'):
                for src in (prep/rev).glob('*.sv'):assert sha(src)==sha(f/rev/src.name)
            if result['healthy']:
                rows+=x.holdout.base.native_audit(f,result)['rows_audited']
                with patch.object(x.old,'CONFIGS',x.holdout.base.CONFIGS):guard=x.all_guard(f/'independent',result,candidate)
                assert tests[arm]==x.holdout.summarize(result,guard)
            else:assert not tests[arm]['passed']
            per_arm[arm]['native_compile_execute']+=2
    else:assert stopped or not any(s['accepted'] for s in states.values())
    assert outcome['independent']==({a:t['passed'] for a,t in tests.items()} if tests else None)
    run100.verify(prep)
    audit=dict(passed=True,native_rows_recomputed=rows,new_model_calls=len(calls),
        unique_new_accepted_versions=outcome['unique_new_accepted_versions'],
        states=states,independent=outcome['independent'],raw_response_verified=True,
        predicates_unchanged=True,requests_rebuilt_exactly=True,feedback_isolation_verified=True,
        rollback_verified=True,budget_verified=True,freeze_before_tests=tests is not None,
        prior_research93_unchanged=True,no_automatic_expansion=True,
        scope='Single seed presentation package pilot, not stable success rate or core mechanism benefit.',script_sha256=sha(Path(__file__)))
    boundaries=[]
    for v in versions:
        if v['reason']!='native_measured':continue
        root=trial/v['arm']/f"v{v['iteration']}"
        candidate=read(root/'model_call/candidate.json');r=read(root/'native/alignment/result.json')
        properties={a['id']:a for a in candidate['assertions']}
        for row in r['ledger']:
            failed=[a for a in row['native']['assertions'] if a['failed'] and properties[a['id']]['timing']=='next_sample']
            if not failed or row['expected']!=0 or row['observed']!=0:continue
            anchor=[s for s in r['reference'] if s['sample_id']==row['sample']['sample_id']-1 and s['configuration']==row['configuration']]
            assert len(anchor)==1
            boundaries.append(dict(arm=v['arm'],iteration=v['iteration'],configuration=row['configuration'],revision=row['revision'],
                anchor=anchor[0],check=row,property=properties[failed[0]['id']],
                scope='Existing native adjacent samples; no modified assertion or new simulation.'))
            break
    out.mkdir(parents=True,exist_ok=False)
    for name,obj in [('audit',audit),('versions',versions),('cost',cost),('cost_by_arm',per_arm),('independent_summary',tests),('boundary_witnesses',boundaries)]:dump(out/f'{name}.json',obj)
    lines=['# research100 / 102 请求呈现对照实际结果','',
        f"实际真实调用 {len(calls)}/4，新完整接受的不同版本 {outcome['unique_new_accepted_versions']}。传输中断 {stopped}。没有自动扩种子。",'',
        'C：原内部候选字段及原始配对记录；T：仅可编辑字段及绑定采样解码表。两组均有失败标记、同一输出白名单和相同配对证据；这是新封存的组合呈现对照，不将research94当作同信息对照。每组最多两次，接受即停，未使用额度不挪用。','',
        '|组/轮|原生回放|完整接受|OP+BRANCH检出/690|新增合法误报|丢失旧检出|',
        '|---|---|---|---:|---:|---:|']
    for v in versions:
        det=sum(v['counts'][c]['detections'] for c in ('history','search')) if v['counts'] else '未执行'
        lines.append(f"|{v['arm']}/{v['iteration']}|{v['reason']}|{v['accepted']}|{det}|{v['new_false_alarms']}|{v['lost_detections']}|")
    lines+=['','|冻结组|独立通过|检出|漏报|误报|unknown|必要未触发|','|---|---|---:|---:|---:|---:|---:|']
    if tests:
        for a,t in tests.items():
            c=t['counts'];lines.append(f"|{a}|{t['passed']}|{c['detections']}|{c['misses']}|{c['false_positives']}|{c['unknown']}|{t.get('required_untriggered')}|")
    else:lines+=['|未启动|无符合条件新接受版本或传输中断||||||']
    lines+=['','如已运行独立测试：两组终态冻结后生成同一批96新指令字、四种配置；开发和旧测试输入均排除。共享测试不算作两个独立总体，采样×配置点不算独立Bug。完整分义务/阶段曝光在independent_summary.json。','',
        '|组|真实调用|输入tokens|输出tokens|原生编译/执行各|','|---|---:|---:|---:|---:|']
    for a,c in per_arm.items():lines.append(f"|{a}|{c['calls']}|{c['prompt_tokens']}|{c['completion_tokens']}|{c['native_compile_execute']}|")
    lines += ['',f"总成本：{cost['model_calls']}次模型调用，输入/输出tokens {cost['prompt_tokens_total']}/{cost['completion_tokens_total']}，原生编译/执行 {cost['native_compile_calls']}/{cost['native_execute_calls']}，编译冒烟{cost['compile_smoke_execute_calls']}；形式化0。准备阶段复用既有18次原生资格执行，不计为新执行。",'',
        f'审计重算{rows}条原生记录，真实响应→性质逐字核验，复建每组实际请求和各自反馈，核对接受/回退与冻结哈希。','',
        '结论边界：首轮/最终接受结果与实际成本可比较；单个固定种子不能证明稳定收益。两组都失败或都通过时，也如实保留，不能把生成成功直接写成呈现改动优势。此对照不是契约搜索或防退化机制增量实验。原生有限仿真不是形式化证明。','',
        '复核（不调用模型）：','```powershell',
        f'wsl -- python3 scripts/research102_presentation_result_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research102_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 实际模型修改轨迹','']
    for a in run100.ARMS:
        trace+=['## '+a,'','初始OP：','```systemverilog']+[v['property'] for v in initial['assertions'][1:]]+['```']
        for v in versions:
            if v['arm']!=a:continue
            trace+=['',f"轮次 {v['iteration']}；接受 {v['accepted']}；{v['reason']}",'```json',json.dumps(v['edit'],ensure_ascii=False,indent=2),'```']
            if v['counts']:trace+=['```json',json.dumps(v['counts'],ensure_ascii=False,indent=2),'```']
            if v['interface_error']:trace+=['原始接口拒绝：'+json.dumps(v['interface_error'],ensure_ascii=False)]
        trace+=['','终态活动OP：','```systemverilog']+[v['property'] for v in active[a]['assertions'][1:]]+['```','']
    if boundaries:
        trace+=['## 下一周期性质的实际误报边界','']
        for b in boundaries:
            anchor=b['anchor'];check=b['check'];w=anchor['instruction'];cw=check['sample']['instruction']
            trace += [f"{b['arm']}/{b['iteration']}：起始sample {anchor['sample_id']}、transaction {anchor['transaction_id']}、指令0x{w:08x}；检查sample {check['sample']['sample_id']}、transaction {check['sample']['transaction_id']}、指令0x{cw:08x}。",
                f"检查采样的参考illegal={check['expected']}，RTL实际illegal={check['observed']}；原生{b['property']['id']}仍报告失败。",
                '```systemverilog',b['property']['property'],'```',
                '性质将前一个采样的义务延伸到下一采样；此处已经切换到另一条合法指令，因而发生误报。相同当前采样表不能替代起始/检查采样的跨周期对应。没有修改此性质后冒充模型恢复。','']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    dump(out/'bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in [prep/'sealed.json',trial/'authorization.json',trial/'outcome.json',trial/'cost.json']})
    print('AUDIT102',audit,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','run','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
