"""Read-only audit of authorized research92 calls, native gates and holdout."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research92_remote_recovery as r
import research88_cross_parent_audit as old_audit

x=r.x
ROOT,read,dump,sha=r.ROOT,r.read,r.dump,r.sha


def response(folder):
    """Reconstruct first-choice model content from persisted upstream bytes."""
    status=read(folder/'transport_result.json')
    assembled=read(folder/'response.assembled.json')['message']['content']
    if status['status']!='response_received':return assembled,dict(status=status['status'],complete=False)
    raw=(folder/'response.stream.raw').read_text(encoding='utf-8')
    if (folder/'response.events.jsonl').exists():
        events=[];lines=[];terminal=False
        for line in raw.splitlines():
            if line.startswith('data:'):lines.append(line[5:].lstrip())
            elif not line and lines:
                text='\n'.join(lines);lines=[]
                if text=='[DONE]':terminal=True;break
                events.append(json.loads(text))
        assert terminal
        assert events==[json.loads(s) for s in (folder/'response.events.jsonl').read_text().splitlines()]
    else:
        events=[json.loads(raw)];assert events[0]==read(folder/'response.server.json')
    content='';finish=None;usage=None
    for event in events:
        if event.get('usage') is not None:usage=event['usage']
        for choice in event.get('choices',[]):
            if choice.get('index',0)!=0:continue
            text=choice.get('delta',choice.get('message',{})).get('content')
            if isinstance(text,str):content+=text
            if choice.get('finish_reason') is not None:finish=choice['finish_reason']
    assert content==assembled and finish=='stop'
    if usage:
        for key in ('prompt_tokens','completion_tokens'):assert status[key]==usage.get(key)
    return content,dict(status=status['status'],complete=True,events=len(events),finish=finish,usage=usage)


def run(prep,trial,out):
    x.verify(prep);r.validate_grant(read(trial/'authorization.json'),prep,trial)
    for n,h in read(prep/'reused_bindings.json').items():assert sha(ROOT/n)==h,n
    out.mkdir(parents=True,exist_ok=False)
    baseline=read(prep/'baseline_full.json');initial=read(prep/'initial.json');proposal=read(prep/'proposal.json')
    assert sha(prep/'proposal.json')==sha(x.SOURCE)
    rows,qual,records=old_audit.inspect_version(r.p.PREVIOUS/'qualification',proposal,baseline)
    shared=x.old.acceptance.inspect(x.paired.aggregate(records['history'],records['search'])['ledger'])
    assert qual['ordinary']['accepted'] and not qual['history']['accepted']
    assert read(trial/'A/initial/active.json')==proposal and read(trial/'B/initial/active.json')==initial
    active=initial;active_full=baseline;feedback=read(prep/'initial_feedback.json')
    seen={x.signature(initial),x.signature(proposal)};versions=[];responses=[];calls=[]
    folders=sorted((trial/'B').glob('v[0-9]*'))
    for folder in folders:
        i=int(folder.name[1:]);call=read(folder/'model_call/result.json');calls.append(call)
        req=read(folder/'model_call/request.json')
        assert req==(read(prep/'request.preview.json') if i==0 else r.payload(proposal,feedback,i))
        assert read(trial/'budget_ledger.json')[i]['request_sha256']==x.old.acceptance.sha(req)
        text,record=response(folder/'model_call');responses.append(record)
        trans=read(folder/'transition/transition.json');candidate=None;ev=None
        if (folder/'model_call/candidate.json').exists():
            value=read(folder/'model_call/model_edit.json');assert json.loads(text)==value
            candidate,_=r.p.TEXT_ADAPT(value,initial)
            assert candidate==read(folder/'model_call/candidate.json')
            assert candidate['assertions'][0]==initial['assertions'][0]
            for supplied,rendered in zip(value['assertions'],candidate['assertions'][1:]):
                assert supplied['antecedent']==rendered['antecedent']
                assert supplied['consequent']==rendered['consequent']
            if (folder/'native/decision.json').exists():
                assert x.signature(candidate) not in seen
                n,ev,records=old_audit.inspect_version(folder/'native',candidate,baseline);rows+=n
                assert trans['accepted']==ev['history']['accepted'] and trans['reason']==ev
                if trans['accepted']:active_full=x.paired.aggregate(records['history'],records['search'])
                proposal=candidate;feedback=x.diagnostics(ev,records)
                seen.add(x.signature(candidate))
            else:
                assert x.signature(candidate) in seen and not trans['accepted']
                feedback=dict(actual_rejection=trans['reason'],actual_model_text=text,previous_verified_diagnostics=feedback)
        else:feedback=dict(actual_rejection=trans['reason'],actual_model_text=text,previous_verified_diagnostics=feedback)
        assert trans['previous_sha256']==x.old.acceptance.sha(active)
        assert read(folder/'transition/active.json')==(candidate if trans['accepted'] else active)
        active=read(folder/'transition/active.json')
        if trans['accepted'] or call['status']!='response_received':assert folder==folders[-1]
        versions.append(dict(iteration=i,accepted=trans['accepted'],decision=trans['reason'],
            native_checked=ev is not None,counts=ev['counts'] if ev else None,
            focus12=ev['current_gate']['focus12'] if ev else None))
    outcome=read(trial/'outcome.json');cost=read(trial/'cost.json')['total']
    assert cost['model_calls']==len(calls)==outcome['actual_model_calls']<=2
    assert len(read(trial/'budget_ledger.json'))==len(calls)
    assert sum(v['accepted'] for v in versions)==outcome['new_accepted_versions']
    assert cost['native_compile_calls']<=16 and cost['native_execute_calls']<=16
    charged=sum((c['prompt_tokens']+c['completion_tokens']) if c.get('prompt_tokens') is not None and c.get('completion_tokens') is not None else c['token_budget_reservation'] for c in calls)
    assert charged<=60000
    assert x.old.acceptance.sha(active)==outcome['active_sha256']
    tests=None
    if (trial/'independent_summary.json').exists():
        assert outcome['new_accepted_versions']==1
        tests=read(trial/'independent_summary.json');freeze=read(trial/'freeze.json')
        generation=read(trial/'generation.json');cases=read(trial/'independent_cases.json')
        assert generation['at']>freeze['time'] and generation['freeze_sha256']==sha(trial/'freeze.json')
        assert cases==x.holdout.base.generate(generation['seed'],read(prep/'excluded_words.json'))
        assert len({t['instruction'] for t in cases})==96 and not {t['instruction'] for t in cases}&set(read(prep/'excluded_words.json'))
        for arm,candidate in (('A',read(prep/'proposal.json')),('B',active)):
            f=trial/'frozen'/arm;result=read(f/'independent/result.json')
            assert read(f/'candidate.json')==candidate and x.old.acceptance.sha(candidate)==freeze['versions'][arm]
            assert read(f/'independent_cases.json')==cases
            for rev in ('before','after'):
                for file in (prep/rev).glob('*.sv'):assert sha(file)==sha(f/rev/file.name)
            rows+=x.holdout.base.native_audit(f,result)['rows_audited']
            with patch.object(x.old,'CONFIGS',x.holdout.base.CONFIGS):guard=x.all_guard(f/'independent',result,candidate)
            assert tests[arm]==x.holdout.summarize(result,guard)
        assert outcome['independent_passed']==tests['B']['passed']
    else:assert outcome['independent_passed'] is None and outcome['new_accepted_versions']==0
    terminal=x.old.acceptance.inspect(active_full['ledger'])
    comparison=dict(retained_target_detections=len(shared['detections']&terminal['detections']),
        lost_target_detections=len(shared['detections']-terminal['detections']),
        removed_legal_false_alarms=len(shared['false_positives']-terminal['false_positives']),
        new_legal_false_alarms=len(terminal['false_positives']-shared['false_positives']))
    protection={ob:dict(detected=sum(v['obligation']==ob and k in terminal['detections'] for k,v in terminal['rows'].items()),
        missed=sum(v['obligation']==ob and k in terminal['misses'] for k,v in terminal['rows'].items())) for ob in x.old.OBLIGATIONS}
    success=bool(outcome['new_accepted_versions'] and tests and tests['B']['passed'])
    assert success==outcome['bounded_recovery_success']
    audit=dict(passed=True,native_rows_recomputed=rows,actual_remote_calls=len(calls),
        new_accepted_versions=outcome['new_accepted_versions'],new_independent_passed=tests['B']['passed'] if tests else None,
        bounded_recovery_success=success,budget_passed=True,raw_response_verified=True,
        model_predicates_unchanged=True,branch_unchanged=True,frozen_before_test=True if tests else None,
        terminal_vs_shared_proposal=comparison,development_protection=protection,
        scope='Selected known historical proposal; conditional recovery, not randomized generation/recovery rate or unique relative-comparator advantage.',
        script_sha256=sha(Path(__file__)))
    for name,value in [('audit',audit),('versions',versions),('responses',responses),('cost',cost),('independent_summary',tests)]:dump(out/f'{name}.json',value)
    lines=['# research92–93：已授权固定预算内的真实模型恢复','',
        f"实际远程调用 **{len(calls)}/2**；新完整接受版本 **{outcome['new_accepted_versions']}**；新独立验收 **{tests['B']['passed'] if tests else '未启动'}**；完整恢复 **{success}**。",'',
        '原始历史案例：Ibex #166 decoder。源RTL及前后提交沿用已核验source_binding.json；不是人工注入故障或整核验证。此前research87/90的各两次本地失败保留，本轮为新封存的Qwen72B两次上限，没有回填旧成功或第三次追加调用。','',
        '固定普通R0接受research61原始真实提案；追加历史R1因636条合法误报拒绝。普通组接受即停，历史组收到允许的开发诊断后继续；两组最多两次追加预算，实际用量不同。相同历史信息的绝对检查同样拒绝，不能宣称相对比较器独有必要性。','',
        '|轮次|接受|完成原生检查|OP+BRANCH检出/690|','|---|---|---|---:|']
    for v in versions:
        detections=sum(v['counts'][c]['detections'] for c in ('history','search')) if v['counts'] else '未执行'
        lines.append(f"|{v['iteration']}|{v['accepted']}|{v['native_checked']}|{detections}|")
    lines+=['',f"相对共同起始提案：保留{comparison['retained_target_detections']}/690目标检出，丢失{comparison['lost_target_detections']}；消除{comparison['removed_legal_false_alarms']}条合法误报，新增误报{comparison['new_legal_false_alarms']}。",'',
        '原始OP性质：','```systemverilog',read(prep/'proposal.json')['assertions'][1]['property'],'```','',
        '终态活动OP性质（仅完整接受后更新，否则保留原基线）：','```systemverilog']
    lines += [a['property'] for a in active['assertions'][1:]]+['```','',
        '全部原始模型响应、可执行表达式、触发/失败标记及接受/回退记录均保留。审计检查响应到表达式逐字不变；没有人工替换位号、补写类别条件或复制归档成功性质。','',
        '|冻结终态|独立通过|检出|漏报|误报|关键unknown|必要未触发|','|---|---|---:|---:|---:|---:|---:|']
    if tests:
        for arm,t in tests.items():
            c=t['counts'];lines.append(f"|{arm}|{t['passed']}|{c['detections']}|{c['misses']}|{c['false_positives']}|{c['unknown']}|{t['required_untriggered']}|")
        lines+=['','两组终态冻结后才生成同一批96个新指令字，四种RV32E/RV32M配置。排除开发数据及research63/85/87/90全部已用编码；旧独立结果仅用于输入去重，不反馈模型。本批没有用于修改或选择候选。分义务、阶段、配置的曝光与触发在independent_summary.json。']
    else:lines+=['|未启动|无新接受版本||||||']
    lines+=['',f"成本：模型{cost['model_calls']}次，输入/输出tokens {cost['prompt_tokens_total']}/{cost['completion_tokens_total']}；原生编译{cost['native_compile_calls']}、实验执行{cost['native_execute_calls']}、编译冒烟执行{cost['compile_smoke_execute_calls']}次；形式化0。归档共同提案与资格回放成本在research61/87账本，本轮没有将复用记作新调用。",'',
        f"审计重算{rows}条原生证据记录。计数是有限采样×配置×版本点，不是独立Bug。此结果是已观察选定案例的条件性恢复；不估计随机新提案成功率、多种子稳定性，也不证明全局无退化。更换模型/表示的效果不能归为门控本身的收益。",'',
        '复核命令（不调用模型）：','```powershell',f'wsl -- python3 scripts/research93_remote_recovery_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research93_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    paths=[prep/'sealed.json',trial/'authorization.json',trial/'outcome.json',trial/'cost.json']
    if tests:paths += [trial/n for n in ('freeze.json','generation.json','independent_cases.json')]
    dump(out/'bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in paths})
    print('AUDIT93',audit,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','run','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
