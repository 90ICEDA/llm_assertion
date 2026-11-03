"""Recompute the bounded text-recovery trial from real responses/native logs."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research90_text_recovery as p
import research88_cross_parent_audit as previous

x=p.x
read,dump,sha,ROOT=p.read,p.dump,p.sha,p.ROOT


def run(prep,trial,out):
    x.verify(prep)
    for name,h in read(prep/'reused_bindings.json').items():assert sha(ROOT/name)==h,name
    out.mkdir(parents=True,exist_ok=False)
    initial=read(prep/'initial.json');proposal=read(prep/'proposal.json');baseline=read(prep/'baseline_full.json')
    assert sha(prep/'proposal.json')==sha(x.SOURCE)
    rows,qualification,records=previous.inspect_version(p.PREVIOUS/'qualification',proposal,baseline)
    shared_info=x.old.acceptance.inspect(x.paired.aggregate(records['history'],records['search'])['ledger'])
    assert qualification['ordinary']['accepted'] and not qualification['history']['accepted']
    assert read(trial/'A/initial/active.json')==proposal
    assert read(trial/'B/initial/active.json')==initial
    feedback=read(prep/'initial_feedback.json');active=initial
    seen={x.signature(initial),x.signature(proposal)};versions=[];calls=[];active_full=baseline
    for folder in sorted((trial/'B').glob('v[0-9]*')):
        i=int(folder.name[1:]);request=read(folder/'model_call/request.json')
        assert request==(read(prep/'request.preview.json') if i==0 else p.request(proposal,feedback,i))
        call=read(folder/'model_call/transport_result.json');calls.append(call)
        transition=read(folder/'transition/transition.json');final=read(folder/'transition/active.json')
        detail=None;candidate=None
        if call['status']=='response_received':
            chunks=[json.loads(line) for line in (folder/'model_call/response.stream.jsonl').read_text().splitlines()]
            text=''.join(c.get('message',{}).get('content','') for c in chunks)
            assert text==read(folder/'model_call/response.raw.json')['message']['content']
            if (folder/'model_call/candidate.json').exists():
                value=read(folder/'model_call/model_edit.json');assert json.loads(text)==value
                candidate,_=p.TEXT_ADAPT(value,initial)
                assert candidate==read(folder/'model_call/candidate.json')
                assert candidate['assertions'][0]==initial['assertions'][0]
                for item,rendered in zip(value['assertions'],candidate['assertions'][1:]):
                    assert item['antecedent']==rendered['antecedent']
                    assert item['consequent']==rendered['consequent']
                if (folder/'native/decision.json').exists():
                    assert x.signature(candidate) not in seen
                    n,detail,records=previous.inspect_version(folder/'native',candidate,baseline);rows+=n
                    assert transition['accepted']==detail['history']['accepted']
                    if transition['accepted']:active_full=x.paired.aggregate(records['history'],records['search'])
                    proposal=candidate;feedback=x.diagnostics(detail,records)
                else:
                    assert not transition['accepted']
                    feedback=dict(actual_model_text=text,actual_rejection=transition['reason'],previous_verified_diagnostics=feedback)
                seen.add(x.signature(candidate))
            else:feedback=dict(actual_model_text=text,actual_rejection=transition['reason'],previous_verified_diagnostics=feedback)
        else:assert not transition['accepted']
        assert transition['previous_sha256']==x.old.acceptance.sha(active)
        assert final==(candidate if transition['accepted'] else active)
        active=final
        versions.append(dict(iteration=i,accepted=transition['accepted'],reason=transition['reason'],
            counts=detail['counts'] if detail else None,
            new_false_alarms=len(detail['new_false_alarm_ids']) if detail else None,
            lost_historical_detections=len(detail['lost_detection_ids']) if detail else None,
            required_untriggered=detail['required_untriggered'] if detail else None,
            focus12=detail['current_gate']['focus12'] if detail else None))
    outcome=read(trial/'outcome.json');cost=read(trial/'cost.json')['total']
    assert len(calls)==outcome['new_calls']==cost['model_calls']<=2
    assert len(read(trial/'budget_ledger.json'))==len(calls)
    assert cost['prompt_tokens_total']+cost['completion_tokens_total']<=30000
    assert cost['native_compile_calls']<=16 and cost['native_execute_calls']<=16
    assert x.old.acceptance.sha(active)==outcome['active_B_sha256']
    tests=read(trial/'independent_summary.json')
    freeze=read(trial/'freeze.json');generation=read(trial/'generation.json');cases=read(trial/'independent_cases.json')
    assert generation['at']>freeze['time'] and generation['freeze_sha256']==sha(trial/'freeze.json')
    assert cases==x.holdout.base.generate(generation['seed'],read(prep/'excluded_words.json'))
    assert len({t['instruction'] for t in cases})==96
    assert not {t['instruction'] for t in cases}&set(read(prep/'excluded_words.json'))
    for arm,expected in (('A',read(prep/'proposal.json')),('B',active)):
        f=trial/'frozen'/arm;candidate=read(f/'candidate.json');r=read(f/'independent/result.json')
        assert candidate==expected and x.old.acceptance.sha(candidate)==freeze['versions'][arm]
        assert read(f/'independent_cases.json')==cases
        audit=x.holdout.base.native_audit(f,r);rows+=audit['rows_audited']
        for rev in ('before','after'):
            for file in (prep/rev).glob('*.sv'):assert sha(file)==sha(f/rev/file.name)
        with patch.object(x.old,'CONFIGS',x.holdout.base.CONFIGS):guard=x.all_guard(f/'independent',r,candidate)
        assert tests[arm]==x.holdout.summarize(r,guard)
    result=dict(passed_audit=True,native_rows_recomputed=rows,new_model_calls=len(calls),
        new_accepted_versions=sum(v['accepted'] for v in versions),
        full_151_accepted=outcome['accepted_B'],independent_passed=tests['B']['passed'],
        bounded_recovery_success=bool(outcome['accepted_B'] and tests['B']['passed']),
        ordinary_accepted_initial=True,historical_rejected_initial=True,
        historical_extra_false_alarms=len(qualification['new_false_alarm_ids']),
        source='Selected and already observed research61 proposal in original Ibex #166.',
        no_global_or_multiseed_success_rate=True,remote_calls=0,formal_calls=0,
        protocol_change='Text expression generation replaces research87 AST output; new two-call pilot, not retroactive success or evidence of mechanism-only gain.',
        script_sha256=sha(Path(__file__)))
    active_info=x.old.acceptance.inspect(active_full['ledger'])
    result['terminal_vs_shared_proposal']=dict(
        retained_target_detections=len(shared_info['detections']&active_info['detections']),
        lost_target_detections=len(shared_info['detections']-active_info['detections']),
        removed_legal_false_alarms=len(shared_info['false_positives']-active_info['false_positives']),
        new_legal_false_alarms=len(active_info['false_positives']-shared_info['false_positives']),
        terminal_counts=active_full['counts'])
    dump(out/'audit.json',result);dump(out/'versions.json',versions);dump(out/'cost.json',cost)
    dump(out/'independent_summary.json',tests)
    lines=['# research90–91：固定两次预算的真实恢复验收','',
        f"新模型调用{len(calls)}/2；新接受版本{result['new_accepted_versions']}；151事务接受={outcome['accepted_B']}；新独立验收={tests['B']['passed']}；完整预算内恢复={result['bounded_recovery_success']}。",'',
        '本轮使用本机qwen2.5-coder:7b-instruct，文本表达式接口；全部OP谓词来自真实响应，既有BRANCH组件原样保留。最多两次，无传输重试、无中途改接口/验收规则，通过即停。research87两次失败不改写；其成本不并入本轮成功率，也不能忽略整个研究的既往尝试。','',
        '共享初始提案是已观察过的research61真实输出。固定普通R0接受；R1在相同目标要求外追加历史检查，发现636条合法误报而拒绝。R0组停止、R1组继续，追加预算上限同为两次，实际花费不等。这个选定案例结果不能估计随机新提案的成功率。相同历史信息的绝对检查也能拒绝初始提案，不能声称相对比较器独有必要性。','',
        '|轮次|接受|开发OP+BRANCH检出/690|开发误报|基线检出丢失|必要未触发|',
        '|---|---|---:|---:|---:|---:|']
    for v in versions:
        total=sum(v['counts'][c]['detections'] for c in ('history','search')) if v['counts'] else '未执行'
        lines.append(f"|{v['iteration']}|{v['accepted']}|{total}|{v['new_false_alarms']}|{v['lost_historical_detections']}|{v['required_untriggered']}|")
    comparison=result['terminal_vs_shared_proposal']
    lines+=['',f"最终活动集合相对共同起始提案：保留{comparison['retained_target_detections']}/690个目标检出，丢失{comparison['lost_target_detections']}，消除{comparison['removed_legal_false_alarms']}条合法误报，新增误报{comparison['new_legal_false_alarms']}。只有新版本被完整接受且独立通过时才算恢复成功。"]
    lines+=['','起始OP性质：','```systemverilog',read(prep/'proposal.json')['assertions'][1]['property'],'```','',
        '最终活动OP性质（真实生成被拒绝时保持旧基线）：','```systemverilog']
    lines += [a['property'] for a in active['assertions'][1:]]+['```','',
        '|冻结终态|独立通过|检出|漏报|误报|关键unknown|必检未触发|','|---|---|---:|---:|---:|---:|---:|']
    for arm,t in tests.items():
        c=t['counts'];lines.append(f"|{arm}|{t['passed']}|{c['detections']}|{c['misses']}|{c['false_positives']}|{c['unknown']}|{t['required_untriggered']}|")
    lines+=['','两组均冻结后生成同一批96个新指令字，四种RV32E/RV32M配置，首周期与保持阶段分开归因。排除全部已有开发输入及research63/85/87已用编码；旧独立结果不送模型。没有根据本轮独立结果修改或选择候选。逐义务、配置和阶段曝光在independent_summary.json中。计数为采样×配置×版本证据点，不是独立Bug。','',
        f"成本：模型{cost['model_calls']}次，输入/输出tokens {cost['prompt_tokens_total']}/{cost['completion_tokens_total']}；原生编译{cost['native_compile_calls']}、实验执行{cost['native_execute_calls']}、编译冒烟执行{cost['compile_smoke_execute_calls']}次。远程及形式化调用0。复用的资格原生日志及原始提案生成成本在research87/research61原账本，不当作本轮新调用。",'',
        f"审计重算{rows}条原生记录；验证模型原始流→JSON→可执行表达式逐字保持、固定BRANCH、R0/R1、预算、反馈、回退、冻结与独立划分。结论限于原始decoder有限样本，不是整核或形式化证明；文本呈现变化的效果不能记为历史门控自身收益。",'',
        '复核（不调用模型）：','```powershell',
        f'wsl -- python3 scripts/research91_recovery_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research91_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    paths=[prep/'sealed.json',trial/'outcome.json',trial/'cost.json',trial/'freeze.json',trial/'generation.json',trial/'independent_cases.json']
    dump(out/'bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in paths})
    print('AUDIT91',result,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','run','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
