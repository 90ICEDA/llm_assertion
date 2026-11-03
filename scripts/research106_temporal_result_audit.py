"""Audit bounded real temporal recovery, including repeated-proposal rejection."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research104_temporal_recovery as r
from research93_remote_recovery_audit import response
from research88_cross_parent_audit import inspect_version

x,p,t=r.x,r.p,r.temporal
ROOT,read,dump,sha=r.ROOT,r.read,r.dump,r.sha


def run(prep,trial,out):
    r.verify(prep);r.grant_check(read(trial/'authorization.json'),prep,trial)
    initial=read(prep/'initial.json');active=initial;current=read(prep/'proposal.json');base=read(prep/'baseline_full.json')
    rows,initial_ev,rec=inspect_version(r.VERSION/'native',current,base)
    qualification_rows=rows;native_folder=r.VERSION/'native';diagnostic=None
    seen={x.signature(initial),x.signature(current)};accepted=False;calls=[];versions=[]
    ledger=read(trial/'budget_ledger.json');assert 1<=len(ledger)<=2
    for i,item in enumerate(ledger):
        assert item['iteration']==i
        folder=trial/f'v{i}';mf=folder/'model_call';req=read(mf/'request.json')
        assert req==t.request(current,rec,native_folder,i,diagnostic)
        if i==0:assert req==read(prep/'request.preview.json')
        assert item['request_sha256']==x.old.acceptance.sha(req)
        assert item['reservation']==sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']<=40000
        body=json.loads(req['messages'][1]['content']);events=body['actual_feedback']['temporal_binding']
        ctx=t.context(native_folder,current,rec)
        for event in events['false_alarm_boundaries']+events['preserve_first_and_held_controls']:assert t.validate(event,ctx)
        text,raw=response(mf);call=read(mf/'result.json');calls.append(call)
        tr=read(folder/'transition/transition.json');candidate=None;ev=None
        if (mf/'candidate.json').exists():
            edit=read(mf/'model_edit.json');assert json.loads(text)==edit
            candidate,_=p.prior.p.TEXT_ADAPT(edit,initial)
            assert candidate==read(mf/'candidate.json') and candidate['assertions'][0]==initial['assertions'][0]
            for a,b in zip(edit['assertions'],candidate['assertions'][1:]):assert all(a[k]==b[k] for k in t.fmt.FIELDS)
            if tr['reason']['kind']=='repeated_executable_proposal':
                assert x.signature(candidate) in seen and not (folder/'native').exists();candidate=None
            else:
                assert tr['reason']['kind']=='native_measured' and x.signature(candidate) not in seen
                seen.add(x.signature(candidate));n,ev,newrec=inspect_version(folder/'native',candidate,base);rows+=n
                assert tr['reason']['decision']==ev
                current=candidate;rec=newrec;native_folder=folder/'native'
        else:assert tr['reason']['kind']=='transport_or_interface'
        accepted=bool(ev and ev['history']['accepted']);assert tr['accepted']==accepted
        assert tr['previous_sha256']==x.old.acceptance.sha(active) and read(folder/'transition/before.json')==active
        assert tr['proposal_sha256']==(x.old.acceptance.sha(candidate) if candidate else None)
        if candidate is not None:assert read(folder/'transition/proposal.json')==candidate
        expected=candidate if accepted else active
        assert read(folder/'transition/active.json')==expected and tr['active_sha256']==x.old.acceptance.sha(expected) and tr['rollback_verified']
        active=expected
        diagnostic=None if ev else dict(reason=tr['reason'],actual_model_text=text)
        versions.append(dict(iteration=i,accepted=accepted,reason=tr['reason']['kind'],raw_response=raw,
            model_edit=read(mf/'model_edit.json') if (mf/'model_edit.json').exists() else None,
            new_native_executed=ev is not None,counts=ev['counts'] if ev else None,
            temporal_false_alarm_examples=len(events['false_alarm_boundaries']),target_controls=len(events['preserve_first_and_held_controls'])))
        if accepted or call['status']!='response_received':assert i==len(ledger)-1
    outcome=read(trial/'outcome.json');cost=read(trial/'cost.json')['total'];tests=None
    assert outcome['actual_calls']==len(calls)==cost['model_calls']<=2
    assert outcome['new_accepted_versions']==int(accepted)
    assert outcome['active_sha256']==x.old.acceptance.sha(active) and read(trial/'terminal/candidate.json')==active
    assert not outcome['automatic_expansion']
    assert outcome['transport_stopped']==any(c['status']!='response_received' for c in calls)
    assert cost['native_compile_calls']<=14 and cost['native_execute_calls']<=14
    assert sum(c['prompt_tokens']+c['completion_tokens'] if c.get('prompt_tokens') is not None and c.get('completion_tokens') is not None else c['token_budget_reservation'] for c in calls)<=80000
    if (trial/'independent_summary.json').exists():
        assert accepted and not outcome['transport_stopped']
        tests=read(trial/'independent_summary.json');freeze=read(trial/'freeze.json');generation=read(trial/'generation.json');cases=read(trial/'independent_cases.json')
        assert generation['at']>freeze['time'] and generation['freeze_sha256']==sha(trial/'freeze.json')
        assert freeze['development_exclusion_sha256']==sha(prep/'excluded_words.json')
        assert freeze['source_sha256']==read(prep/'source_binding.json')['source_sha256']
        assert cases==x.holdout.base.generate(generation['seed'],read(prep/'excluded_words.json'))
        assert len({c['instruction'] for c in cases})==96 and not {c['instruction'] for c in cases}&set(read(prep/'excluded_words.json'))
        f=trial/'frozen/recovered';result=read(f/'independent/result.json')
        assert read(f/'candidate.json')==active and freeze['versions']['recovered']==x.old.acceptance.sha(active)
        assert read(f/'independent_cases.json')==cases
        for rev in ('before','after'):
            for src in (prep/rev).glob('*.sv'):assert sha(src)==sha(f/rev/src.name)
        if result['healthy']:
            rows+=x.holdout.base.native_audit(f,result)['rows_audited']
            with patch.object(x.old,'CONFIGS',x.holdout.base.CONFIGS):guard=x.all_guard(f/'independent',result,active)
            assert tests['recovered']==x.holdout.summarize(result,guard)
        else:assert not tests['recovered']['passed']
    else:assert not accepted
    assert outcome['independent']==tests
    r.verify(prep);out.mkdir(parents=True,exist_ok=False)
    audit=dict(passed=True,raw_response_verified=True,exact_predicates_verified=True,request_rebuilt_exactly=True,
        temporal_feedback_native_binding_verified=True,budget_verified=True,rollback_verified=True,
        raw_native_rows_recomputed=rows,reused_qualification_rows=qualification_rows,new_calls=len(calls),
        new_accepted_versions=int(accepted),independent=tests,no_expansion=True,prior_records_unchanged=True,script_sha256=sha(Path(__file__)))
    for name,obj in [('audit',audit),('versions',versions),('cost',cost),('independent_summary',tests)]:dump(out/f'{name}.json',obj)
    lines=['# research104 / 106：绑定时序反例后的真实恢复结果','',
        f"真实调用{len(calls)}/2；新接受版本{int(accepted)}；新独立测试{'已执行' if tests else '未启动'}。未追加调用或扩种子。",'',
        '任务为已观察的research100 T误报提案的选定恢复。420 OP＋270 BRANCH检出及104条历史/搜索误报是旧提案的原生事实，不记作本轮新增运行。当前小范围另有6条误报。研究100结果和预算保持不变。','',
        '|轮次|拒绝/执行原因|新原生执行|完整接受|时序误报窗口/保护控制|','|---|---|---|---|---|']
    for v in versions:lines.append(f"|{v['iteration']}|{v['reason']}|{v['new_native_executed']}|{v['accepted']}|{v['temporal_false_alarm_examples']}/{v['target_controls']}|")
    lines+=['','请求中的每条事件均重新核对原生起始TRIGGER、后件检查ASSERT_FAIL、检查周期自身cover，以及两周期的事务编号、指令、输出和配置。没有靠补写解释构造成功，也没有手工删除下一周期性质。','',
        f"成本：输入/输出tokens {cost['prompt_tokens_total']}/{cost['completion_tokens_total']}；新增原生编译/执行 {cost['native_compile_calls']}/{cost['native_execute_calls']}，编译冒烟 {cost['compile_smoke_execute_calls']}；形式化0。审计重算{rows}条既有/实际原生记录，不记作新仿真。",'',
        '失败/重复版本不激活；回退保留旧部分BRANCH基线，不能将其声称为完整修复。没有完整接受就不生成独立测试。此前research93成功版本及独立结果不变。', '',
        '本实验只能回答这一选定案例在固定两次预算内是否恢复；不能估计稳定成功率，也不能把恢复/拒绝本身计为两个核心机制的额外收益。', '',
        '复核（无模型调用）：','```powershell',
        f'wsl -- python3 scripts/research106_temporal_result_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research106_audit_NEW','```']
    if tests:lines+=['','独立结果：','```json',json.dumps(tests,ensure_ascii=False,indent=2),'```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 实际模型响应与活动版本','']
    for v in versions:
        trace += [f"轮次{v['iteration']}：{v['reason']}，接受={v['accepted']}",'```json',json.dumps(v['model_edit'],ensure_ascii=False,indent=2),'```','']
    trace+=['终态活动OP性质：','```systemverilog']+[a['property'] for a in active['assertions'][1:]]+['```','仅完整接受时更新活动版本；此处不是把失败提案当作已接受。']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    dump(out/'bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in [prep/'sealed.json',trial/'authorization.json',trial/'outcome.json',trial/'cost.json']})
    print('AUDIT106',audit,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','run','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
