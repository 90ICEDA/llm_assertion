"""Read-only audit of the bounded real research179 run; never dispatch a model."""
import argparse
from pathlib import Path
import json
import research179_frame_controller as c


def audit(prep,run,out):
    c.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        c.dump(out/'checks.json',checks)
        assert value,name
    outcome=c.read(run/'outcome.json');ledger=c.read(run/'budget_ledger.json')
    grant=c.read(run/'authorization.json');c.validate_grant(grant,c.sha(prep/'seal.json'),c.rel(run))
    check('purpose/seal/output bound authorization',True)
    attempts=list(run.rglob('attempt.json'));check('exactly one physical call',len(attempts)==1)
    check('only shared reservation',[x['path'] for x in ledger['reserved_calls']]==['shared'])
    check('no recovery or independent path',not (run/'recovery').exists() and not (run/'independent').exists())
    check('no recovery freeze',not (run/'terminal_freeze.json').exists())
    call=run/'shared/model_call';request=c.read(call/'request.json');preview=c.read(prep/'request.preview.json')
    for key,value in preview.items():check('unchanged request '+key,request.get(key)==value)
    check('ledger matches sealed request',ledger['reserved_calls'][0]['request_hash']==c.digest(preview))
    result=c.read(call/'result.json');transport=c.read(call/'transport_result.json')
    check('real response and terminal',result['status']=='response_received' and result['stream_terminal_received'])
    check('model and no retries',result['actual_server_model']==c.MODEL and result['retries']==0)
    candidate=c.read(call/'candidate.json');edit=c.read(call/'model_edit.json')
    check('model predicates preserved verbatim',candidate==edit['assertions'] and candidate==c.adapt(edit))
    check('usable candidate stage result',result['candidate_status']=='expressions_preserved')
    # Transport record precedes frontend decoding; it is not the final candidate status.
    check('transport record timing is explicit',transport['candidate_status']=='not_generated')
    rows=c.read(prep/'development.json');protected=c.read(prep/'protected.json')
    measured=c.measure(candidate,run/'shared/native',rows,protected)
    saved=c.read(run/'shared/evaluation.json')
    for key in ('ordinary','history','unknown','lost','new_false','public_targets','history_targets','detected','public_missed','history_missed','public_untriggered','history_untriggered'):
        a,b=measured[key],saved[key]
        check('recomputed verdict '+key,sorted(a)==sorted(b) if isinstance(a,list) else a==b)
    detected=set(measured['detected'])
    check('current detection2/2',len(measured['public_targets'])==2 and set(measured['public_targets'])<=detected)
    check('historical detection6/6',len(measured['history_targets'])==6 and set(measured['history_targets'])<=detected)
    check('eight false alarms and no critical unknown',len(measured['new_false'])==8 and not measured['unknown'])
    check('no lost protection or missed target trigger',not measured['lost'] and not measured['public_untriggered'] and not measured['history_untriggered'])
    branch=c.branch(result['status'],True,measured['ordinary'],measured['history'],len(measured['lost']),len(measured['new_false']),len(measured['unknown']))
    check('ordinary rejection stops all further work',branch==outcome['status']=='stop_ordinary_rejects')
    check('no successful or conditional recovery counted',not outcome['full_recovery_accepted'] and not outcome['real_chain_success'] and outcome['conditional_recovery_denominator']==outcome['conditional_recovery_numerator']==0 and outcome['independent'] is None)
    initial=c.read(prep/'initial.json');terminal=c.read(run/'terminal_versions.json');decision=c.read(run/'shared_decision.json')
    for arm in ('O','H'):
        check('unchanged old version '+arm,terminal[arm]==initial and decision['active_hashes'][arm]==c.digest(initial))
    check('old detection list retained',decision['retained_old_detection_ids']==protected)
    counts=[];witnesses=[];bindings={}
    for cfg in (0,1):
        for rev in ('before','after'):
            folder=run/'shared/native'/str(cfg)/rev;n=c.read(folder/'result.json')
            check(f'{cfg}/{rev} native compile/support/execute',n['compile_status']=='passed' and n['execution_status']=='completed' and n['tool_support_status']=='supported_for_compiled_constructs')
            check(f'{cfg}/{rev} exact rendered model assertions',(folder/'tb.sv').read_text()==c.bench(candidate,cfg,rows))
            data=measured['evidence'][f'{cfg}/{rev}'];tr=data['trace']
            for alarm in data['alarms']:
                if alarm['verdict']!='false_positive':continue
                cy=alarm['cycle'];f=next(f for f in data['frames'] if f['check_cycle']==cy)
                check(f'{cfg}/{rev}/{cy} legitimate multi-beat frame',len(f['accepted'])>1 and f['status']=='pass' and f['expected_length']==tr[cy]['length'])
                witnesses.append(dict(config=cfg,revision=rev,label=alarm['label'],frame=f,
                    anchor=tr[f['anchor_cycle']],check=tr[cy],
                    erroneous_expected_last_beat_only=f['beat_bytes'],correct_expected_frame_bytes=f['expected_length']))
            reset=next(m for m in measured['mapping'] if m['config']==cfg and m['revision']==rev and m['label']=='reset_clears_outputs')
            check(f'{cfg}/{rev} reset property vacuity recorded',not reset['trigger_cycles'] and not reset['alarms'])
            counts.append(dict(config=cfg,revision=rev,frames=len(data['frames']),native_failure_markers=len(n['failures']),
                mapped_false_alarms=sum(a['verdict']=='false_positive' for a in data['alarms']),
                mapped_target_alarms=sum(a['verdict']=='target_detection' for a in data['alarms']),
                reset_property_effective_triggers=0))
    cost=c.costs(run,'real');check('actual costs recomputed',cost==c.read(run/'cost.json'))
    check('four compiles and executions',cost['native_compiles']==cost['native_executions']==4)
    check('actual tokens recorded',cost['prompt_tokens']==5539 and cost['completion_tokens']==494)
    c.dump(out/'false_positive_witnesses.json',witnesses);c.dump(out/'native_counts.json',counts);c.dump(out/'cost.json',cost)
    c.dump(out/'milestones.json',dict(new_accepted_versions=0,original_native_pairs_completed=4,current_detected=2,current_total=2,
        history_detected=6,history_total=6,false_alarm_samples=8,critical_unknown=0,extra_history_rejections=0,
        conditional_recovery={'success':0,'eligible':0,'rate':None},independent_executed=False,model_calls_used=1,
        unused_calls=1,unused_call_condition='Only qualified recovery in this sealed run; branch not met. Not permission for a new attempt or changed protocol.'))
    for p in run.rglob('*'):
        if p.is_file() and 'obj_dir' not in p.parts:bindings[c.rel(p)]=c.sha(p)
    bindings.update({c.rel(prep/'seal.json'):c.sha(prep/'seal.json'),c.rel(Path(__file__)):c.sha(Path(__file__))})
    c.dump(out/'source_bindings.json',bindings)
    report=f'''# research179 真实受限先导：普通检查拒绝，按协议停止

本轮实际使用1/2次授权调用，新增接受版本0。真实模型补上当前目标2/2，并保持历史目标6/6，必要目标触发均有记录；但对合法多拍帧产生8条误报。普通与历史规则均拒绝，不存在额外历史拒绝机会。第二次调用未启动，未冻结新接受版本、未抽取或执行32个独立场景。

## 具体失败

模型新增 `finish && !prev_complete |=> frame_len_valid && frame_len == $past(beat_bytes)`，把“前一周期未完成帧”误当作“当前帧只有一拍”。该条件也适用于正常多拍帧的最后一拍，因此错误地只比较最后一拍字节数。

KEEP启用32位时，cycle12接受一个三拍帧的尾拍：此前累计8字节、当前3字节；cycle13原版与修复版均正确报告11，但模型性质要求3。另一个两拍帧cycle23接受尾拍，cycle24正确报告6、性质要求2。KEEP关闭8位时对应为3对1及2对1。两帧×两配置×前后版本，共8个误报采样点，不是8个独立Bug。逐拍接受、起始/检查采样及参考计数见 false_positive_witnesses.json。

模型还增加 `rst |-> ...`，但所有性质包装为 `disable iff(rst)`，该性质没有有效触发，不能计为复位保护。它不是本次接受失败的替代解释；已确认的8条合法误报足以使普通规则拒绝。

模型原始响应、修改理由、JSON性质、可执行tb.sv、工具版本、命令、原始日志及波形均在运行目录。最终调用 result.json 标记 expressions_preserved；transport_result.json 在接口解码之前写入，其 not_generated 是阶段状态，不能据此误判没有候选。未人工修改模型谓词。

## 接受决定与机制含义

O=false、H=false，终态 stop_ordinary_rejects。两组都保留初始部分集合及其6个旧检出；因此当前2个目标在活动旧版本上仍漏报。拒绝未接受提案不等于新问题已经修复。

额外历史拒绝0，条件恢复0/0不可估计，新独立通过数不可估计。该结果不证明防退化的增量恢复价值，也不是其失效结论；本轮没有进入可区分分支。H/R等价限制、576次搜索负结果和旧独立验收结果均未改变。

剩余1次仅用于本协议已限定的条件恢复；条件未成立，不能挪作追加生成或改提示重试。本路线本轮结束，不扩种子。

## 实际成本与核验

1次 DeepSeek V3-0324 调用，无重试；输入5539、输出494 tokens；模型等待{result['wall_seconds']:.3f}秒；4次原生编译、4次执行，编译{cost['compile_seconds']:.3f}秒、执行{cost['execute_seconds']:.3f}秒；形式化查询0。{len(checks)}项结果复核通过。仿真和手写接口预检不构成形式化证明或模型恢复成功。

实际执行命令（已完成；不要用此命令重试旧输出目录）：
```powershell
wsl -- python3 scripts/research179_frame_controller.py run --prepared {c.rel(prep)} --out {c.rel(run)} --authorization deliverables/research179_authorization_20261029_r01.json
```

可复制的本地只读复核（报告目录必须未存在，无模型调用）：
```powershell
wsl -- python3 scripts/research179_result_audit.py --prepared {c.rel(prep)} --run {c.rel(run)} --out deliverables/research179_result_recheck
```
'''
    (out/'SUMMARY.md').write_text(report,encoding='utf-8')
    c.q.seal(out);c.verify(prep)
    print('AUDITED179',len(checks),'checks; accepted0 O/H both reject; calls1; no recovery/independent',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('prepared','run','out'):parser.add_argument('--'+name,required=True,type=Path)
    a=parser.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
