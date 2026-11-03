"""Read-only audit of the sealed presentation trial and frozen holdout results."""
import argparse
from collections import Counter
import json
from pathlib import Path
import research181_presentation_control as s

c=s.c


def audit(prep,run,out):
    s.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)));c.dump(out/'checks.json',checks);assert value,name
    grant=c.read(run/'authorization.json');s.validate_grant(grant,c.sha(prep/'seal.json'),c.rel(run));check('new scope bound grant',True)
    outcome=c.read(run/'outcome.json');ledger=c.read(run/'budget_ledger.json');terminal=c.read(run/'terminal_versions.json');freeze=c.read(run/'all_terminal_frozen.json')
    rows=c.read(prep/'development.json');protected=c.read(prep/'protected.json');initial=c.read(prep/'initial.json')
    expected_requests={a:c.read(prep/a/'request.preview.json') for a in s.ARMS}
    check('initial information equality',s.normalize(expected_requests['C'],'C')==s.normalize(expected_requests['T'],'T'))
    check('two physical calls only',len(list(run.rglob('attempt.json')))==len(ledger['calls'])==2)
    check('no refinement actually run',all(x['round']==0 for x in ledger['calls']) and all(not (run/'arms'/a/'r1').exists() for a in s.ARMS))
    summaries=[];examples=[];bindings={};usage=[]
    for arm in s.ARMS:
        path=run/'arms'/arm/'r0';call=path/'model_call';request=c.read(call/'request.json')
        for key,value in expected_requests[arm].items():check(arm+' unchanged sealed request '+key,request[key]==value)
        entry=next(x for x in ledger['calls'] if x['arm']==arm)
        check(arm+' reservation bound to payload',entry['request_hash']==c.digest(expected_requests[arm]))
        result=c.read(call/'result.json');candidate=c.read(call/'candidate.json');edit=c.read(call/'model_edit.json')
        check(arm+' real complete unmodified model response',result['status']=='response_received' and result['stream_terminal_received'] and result['retries']==0 and result['candidate_status']=='model_expressions_preserved' and candidate==edit['assertions'])
        check(arm+' same model/seed',result['actual_server_model']==c.MODEL and request['seed']==16507)
        ev=c.measure(candidate,path/'native',rows,protected);saved=c.read(path/'evaluation.json')
        for key in ('ordinary','history','unknown','lost','new_false','public_targets','history_targets','detected','public_missed','history_missed','public_untriggered','history_untriggered'):
            a,b=ev[key],saved[key];check(arm+' recomputed '+key,sorted(a)==sorted(b) if isinstance(a,list) else a==b)
        decision=s.decide(result['status'],True,c.signature(candidate)==c.signature(initial),ev,0)
        check(arm+' sealed stopping decision',decision==c.read(path/'decision.json')['action']==outcome['terminal'][arm]['status'])
        check(arm+' terminal candidate choice',terminal[arm]['candidate']==(candidate if ev['history'] else initial))
        check(arm+' frozen hash',freeze['hashes'][arm]==c.digest(terminal[arm]['candidate']))
        for cfg in (0,1):
            for rev in ('before','after'):
                p=path/'native'/str(cfg)/rev;n=c.read(p/'result.json')
                check(f'{arm}/{cfg}/{rev} native complete',n['compile_status']=='passed' and n['execution_status']=='completed')
                check(f'{arm}/{cfg}/{rev} exact executable model source',(p/'tb.sv').read_text()==c.bench(candidate,cfg,rows))
        detected=set(ev['detected']);stats=dict(arm=arm,accepted=ev['history'],action=decision,
            current_detected=len(set(ev['public_targets'])&detected),current_total=len(ev['public_targets']),
            history_detected=len(set(ev['history_targets'])&detected),history_total=len(ev['history_targets']),
            false_alarm_records=len(ev['new_false']),critical_unknown_records=len(ev['unknown']),lost=len(ev['lost']),
            generation_cost=c.costs(path,'real'),service_seconds=result['wall_seconds'])
        summaries.append(stats);usage.append(dict(arm=arm,prompt_tokens=result['prompt_tokens'],completion_tokens=result['completion_tokens']))
        # Store a small original development window, not a hand-repaired SVA.
        traces=ev['evidence'];f=next(f for f in traces['1/after']['frames'] if f['check_cycle']==13)
        examples.append(dict(arm=arm,model_assertions=candidate,model_reason=edit['reason'],accepted=f['accepted'],
            anchor=traces['1/after']['trace'][12],check=traces['1/after']['trace'][13],
            mapped_alarms=[x for x in traces['1/after']['alarms'] if x['cycle'] in (13,14)],
            observation='C checks past sampled sum; T next-sample expression reads current acc_bytes/beat_bytes. Native outcomes, not this explanation, determine acceptance.'))
    check('C accepted and T unknown stop observed',terminal['C']['accepted'] and terminal['T']['status']=='stop_unknown')
    check('no T independent tests',not (run/'arms/T/independent').exists())
    check('one actual new accepted version',outcome['new_real_accepted_versions']==1)
    independent=[];exposure=[]
    for arm in s.ARMS:
        if not terminal[arm]['accepted']:continue
        path=run/'arms'/arm;folder=path/'independent';selected=c.read(folder/'selected.json');result=c.read(folder/'result.json')
        armfreeze=c.read(path/'terminal_freeze.json');candidate=terminal[arm]['candidate']
        check(arm+' all terminals frozen before selection',freeze['time']<=(folder/'selected.json').stat().st_mtime)
        check(arm+' all terminal freeze binding',armfreeze['all_terminal_freeze']==c.sha(run/'all_terminal_frozen.json'))
        check(arm+' candidate unchanged after tests',armfreeze['H']==c.digest(candidate)==freeze['hashes'][arm])
        check(arm+' exactly32 selected no rerolls',len(selected)==32 and result['rerolls']==0)
        strata=Counter((d['config'],d['stratum']) for d in selected)
        check(arm+' fixed eight strata',strata==Counter({(cfg,k):4 for cfg in (0,1) for k in ('historical','current','legal','reset')}))
        capacity=c.pools();inputs={};ranges={}
        for cfg in (0,1):
            cr=[];rs=[]
            for d in selected:
                if d['config']!=cfg:continue
                check(arm+' descriptor in prespecified capacity '+str(d),d in capacity[f'{cfg}/{d["stratum"]}'])
                seq=c.scenario(d);start=len(cr);cr.extend(dict(v,cycle=start+i) for i,v in enumerate(seq));rs.append((start,len(cr),d))
            inputs[cfg]=cr;ranges[cfg]=rs
            check(f'{arm}/{cfg} exact frozen generated inputs',cr==c.read(folder/f'inputs_{cfg}.json'))
            for rev in ('before','after'):
                p=folder/'native'/str(cfg)/rev;n=c.read(p/'result.json')
                check(f'{arm}/{cfg}/{rev} independent native complete',n['compile_status']=='passed' and n['execution_status']=='completed')
                check(f'{arm}/{cfg}/{rev} frozen executable unchanged',(p/'tb.sv').read_text()==c.bench(candidate,cfg,cr))
        ev=c.measure_variable(candidate,folder/'native',inputs,[]);saved=c.read(folder/'evaluation.json')
        for key in ('history','ordinary','unknown','lost','new_false','public_targets','history_targets','detected','public_missed','history_missed','public_untriggered','history_untriggered'):
            a,b=ev[key],saved[key];check(arm+' independent verdict '+key,sorted(a)==sorted(b) if isinstance(a,list) else a==b)
        signatures=set()
        for cfg,rs in ranges.items():
            data=ev['evidence'][f'{cfg}/before'];fixed=ev['evidence'][f'{cfg}/after']
            for start,end,d in rs:
                frames=[f for f in data['frames'] if start<=f['anchor_cycle']<end]
                failures=[f for f in frames if f['status']=='violation'];trace=data['trace'][start:end]
                cancelled=[x for x in data['cancelled'] if start<=x['cycle']<end]
                fpframes=[f for f in fixed['frames'] if start<=f['anchor_cycle']<end]
                signature=(cfg,c.semantic_key(c.scenario(d),cfg));signatures.add(signature)
                check(arm+' new semantic prefix '+str((cfg,start)),max(len(f['accepted']) for f in frames)>3 and signature[1]!=c.semantic_key(rows,cfg))
                required=d['stratum']
                present=any(f['context']==('adjacent' if required=='historical' else 'separated') for f in failures) if required in ('historical','current') else not failures
                check(arm+' actual class exposure '+str((cfg,start,required)),present and bool(frames))
                if required=='reset':check(arm+' actual reset cancellation '+str((cfg,start)),bool(cancelled))
                check(arm+' actual backpressure '+str((cfg,start)),any(v['v'] and not v['r'] for v in trace))
                check(arm+' correct fixed outputs '+str((cfg,start)),all(f['status']=='pass' for f in fpframes))
                exposure.append(dict(arm=arm,config=cfg,start=start,stratum=required,target_points=len(failures),
                    completed_frames=len(frames),reset_cancellations=len(cancelled),signature=signature[1]))
        check(arm+'32 distinct fresh configured scenarios',len(signatures)==32)
        check(arm+' full finite independent pass',result['passed'] and ev['history'] and not ev['unknown'] and not ev['new_false'])
        independent.append(dict(arm=arm,scenario_passed=32,scenario_total=32,current_target_points=len(ev['public_targets']),
            historical_target_points=len(ev['history_targets']),target_missed=len(ev['public_missed'])+len(ev['history_missed']),
            false_alarm_records=len(ev['new_false']),critical_unknown_records=len(ev['unknown']),
            reset_scenarios=sum(x['stratum']=='reset' for x in exposure),
            completion_valid_target_violations=0,completion_valid_scope='Legal behavior checked; original repair does not expose a completion-valid fault. No new validity-fault coverage claimed.',
            cost=c.costs(folder,'local')))
    cost=c.costs(run,'real');check('aggregate actual cost',cost==c.read(run/'cost.json'))
    check('twelve native jobs',cost['native_compiles']==cost['native_executions']==12)
    c.dump(out/'arm_results.json',summaries);c.dump(out/'independent_results.json',independent);c.dump(out/'actual_exposure.json',exposure)
    c.dump(out/'case_traces.json',examples);c.dump(out/'cost.json',cost)
    c.dump(out/'milestones.json',dict(new_model_accepted_versions=1,new_complete_development_replays=2,new_independent_passed_versions=1,
        independent_scenarios_passed=32,model_calls=2,refinement_calls=0,extra_history_rejections=0,
        conditional_history_recovery={'success':0,'eligible':0,'rate':None},
        treatment_superiority_supported=False,scope='One fixed seed, one original frame_len historical repair, public generation capability only.',
        unused_authorized_calls=2,unused_calls_not_transferable=True))
    tab='\n'.join(f'|{v["arm"]}|{v["action"]}|{v["current_detected"]}/{v["current_total"]}|{v["history_detected"]}/{v["history_total"]}|{v["false_alarm_records"]}|{v["critical_unknown_records"]}|{v["generation_cost"]["prompt_tokens"]}/{v["generation_cost"]["completion_tokens"]}|' for v in summaries)
    summary=f'''# research181 采样呈现能力对照：C接受并独立通过，T拒绝停止

实际使用2/4次授权调用：C、T各1次，均未进入细化。新增真实模型接受版本1个；C冻结后32/32新独立场景通过。显式对齐表T未优于嵌套记录C，此结果不支持表格呈现收益，也不能由单个种子推出一般优劣。

|组|终态|开发当前检出|开发历史检出|合法误报记录|关键unknown记录|输入/输出tokens|
|---|---|---|---|---|---|---|
{tab}

两组首次请求除采样呈现外事实等价、初始候选/模型/采样及原生标准相同。两组共同新增了接口说明，因此不能把C相对research179的变化归因于某一句说明。实际请求、模型原响应、每组SVA和执行日志均保留，没有人工修改谓词。

## 两个实际提案

C生成 `finish |=> frame_len == $past(acc_bytes + beat_bytes)` 等性质。在三拍合法帧cycle12累计8字节、尾拍3字节，cycle13正确比较11；原始错误轨迹仍报错。C通过当前2/2、历史6/6，无合法误报、关键unknown和必要目标空触发，首轮接受即停。

T生成next_sample性质却直接读取检查周期的 `acc_bytes + beat_bytes`，另要求完成有效标记在无新finish后继续保持，并在非完成周期限制长度清零。实际出现合法误报，以及长度义务在非完成采样不适用时的报警。封存判定把后者保留为unknown，未强行归入检出或误报；按 stop_unknown 终止该组，不给第二次修正。目标采样虽全部报警，也不足以接受错误约束。

## 冻结后独立验收

两组终态先冻结，只有C接受集合进入测试；T保留原部分基线，未进行独立测试。C在两个KEEP/位宽配置、相邻目标/间隔目标/合法多拍/复位取消八个分层各4场景，共32/32通过；同批目标共16个采样点（当前8、历史8），误报、漏报及关键unknown均0，必要目标触发通过。审计额外确认每个场景的真实背压、8个复位场景的实际取消及新语义前缀长度，未补抽。

本轮原始修复曝光的是帧长度错误。completion_valid仅验证合法行为，没有该义务的目标故障曝光，不能据此声称所有可能有效标记错误都被覆盖。结论限于原始frame_len模块、预定配置和有限仿真；不是形式化证明。独立数据保持独立，未回送模型或选择候选。

## 机制结论及停止

该实验完成了公共生成能力的受控先导，C在这一个范围内取得可用版本；没有表格处理优势证据。两组都使用同一完整历史门控，本轮没有前瞻性“普通接受、历史额外拒绝、恢复”实验，不能把C接受当作防退化增量。真实条件恢复仍0/0不可估计，H/R等价限制与576次搜索负结果保持不变。

本批已结束，不扩种子、不使用剩余2次调用追加修改T。未来若继续，应先固定经过验收的公共生成流程，再另行封存机制先导；不能将本批独立结果拿去挑选新候选或调整规则而仍称独立。

## 成本与复核

实际模型调用{cost['model_calls']}次，输入{cost['prompt_tokens']}、输出{cost['completion_tokens']} tokens；12次原生编译/执行（开发8、C独立4），编译{cost['compile_seconds']:.3f}秒、执行{cost['execute_seconds']:.3f}秒，形式化0。T输入token较少但未通过接受，不能只按token减少宣称有效成本优势。{len(checks)}项结果审计通过。

实际执行命令（已完成，旧目录不允许重试）：
```powershell
wsl -- python3 scripts/research181_presentation_control.py run --prepared {c.rel(prep)} --out {c.rel(run)} --authorization deliverables/research181_authorization_20261030_r01.json
```
可复制本地复核（输出目录必须未存在，无模型调用）：
```powershell
wsl -- python3 scripts/research181_result_audit.py --prepared {c.rel(prep)} --run {c.rel(run)} --out deliverables/research181_result_recheck
```
'''
    (out/'SUMMARY.md').write_text(summary,encoding='utf-8')
    for p in run.rglob('*'):
        if p.is_file() and 'obj_dir' not in p.parts:bindings[c.rel(p)]=c.sha(p)
    for p in (prep/'seal.json',Path(__file__)):bindings[c.rel(p)]=c.sha(p)
    c.dump(out/'source_bindings.json',bindings);c.q.seal(out);s.verify(prep)
    print('AUDITED181',len(checks),'checks; C independent32/32; T rejected; calls2',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for key in ('prepared','run','out'):ap.add_argument('--'+key,required=True,type=Path)
    a=ap.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
