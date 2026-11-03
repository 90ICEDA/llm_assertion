"""Read-only audit of the authorized research189 run; no model or simulation."""
import argparse
import json
from pathlib import Path
import sys

import research189_drop_transport as r

s,p,b,ROOT=r.s,r.p,r.b,r.ROOT


def audit(prep,run,out):
    if not (run/'outcome.json').is_file():raise ValueError('run_not_terminal')
    out.mkdir(parents=True,exist_ok=False)
    def guard(event,args):
        if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('offline_audit')
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(args[0]).resolve();name=path.as_posix().lower();mode=args[1]
            if '/.secrets/' in name or '/.env' in name:raise RuntimeError('no_credentials')
            if isinstance(mode,str) and any(x in mode for x in 'wax+') and path.is_relative_to(p.q.D) and not path.is_relative_to(out):raise RuntimeError('immutable_run')
    sys.addaudithook(guard)
    checks=[]
    def ck(name,condition):
        checks.append(dict(name=name,passed=bool(condition)));s.dump(out/'checks.json',checks);assert condition,name
    r.verify(prep);ck('preparation/source seals unchanged',True)
    outcome=s.read(run/'outcome.json');cost=s.read(run/'cost.json');budget=s.read(run/'budget.json')
    ck('real execution mode',outcome['mode']=='real_model')
    ck('actual cost recounted',r.costs(run,True)==cost)
    ck('bounded authorized submissions',cost['model_calls']<=2 and len(budget['reservations'])<=2)
    actual=s.read(run/'authorization.json');ck('grant tied to exact preparation',actual['authorized'] is True and actual['prepared_sha256']==s.sha(prep/'seal.json') and actual['purpose']==r.PURPOSE)
    request=s.read(prep/'request.preview.json');initial=json.loads(request['messages'][1]['content'])['current_assertions']
    protected=s.read(r.SOURCE/'pilot_protocol.json')['protected_ids'];stage_rows=[];traces=[]
    for stage in ('shared','recovery'):
        folder=run/stage
        if not folder.exists():continue
        call=folder/'model_call'
        if not (call/'result.json').exists():continue
        result=s.read(call/'result.json')
        ck(stage+' no retries',result['retries']==0)
        sent=s.read(call/'request.json')
        ck(stage+' exact pending payload',sent==s.read(folder/'request.preview.json'))
        if stage=='shared':ck('first exact sealed request',sent==request)
        ck(stage+' exact model sampling',sent['model']==r.CONFIG['remote_model'] and sent['temperature']==0.2 and sent['max_tokens']==1024 and sent['seed']==16507+(stage=='recovery'))
        ck(stage+' timeout within cap',s.read(call/'generation_config.json')['timeout_seconds']<=300)
        if not (call/'candidate.json').exists():continue
        candidate=s.read(call/'candidate.json');raw=s.read(call/'model_edit.json')
        ck(stage+' model expressions preserved',p.adapt(raw)==candidate)
        if not (folder/'native/measurement.json').exists():continue
        jobs=s.read(folder/'native/executions.json');record=s.read(folder/'native/measurement.json')
        measure=b.bound_measure(candidate,jobs,protected)
        ck(stage+' independent replay of acceptance matches',record==json.loads(json.dumps(measure)))
        ck(stage+' full development population',len(jobs)==12 and len({(j['depth'],j['policy'],j['revision']) for j in jobs})==12)
        for job in jobs:
            path=Path(job['folder']);key=f"{stage}/{job['scene_id']}/{job['revision']}"
            ck(key+' result log bound',s.read(path/'result.json')==job['result'])
            ck(key+' exact generated bench', (path/'tb.sv').read_text()==p.bench(candidate,job['depth'],job['policy'],job['rows']))
        for key,ref in measure['reference'].items():
            for event in ref['events']:
                eid=key.rsplit('/',1)[0]+f"/frame{event['frame']}"
                traces.append(dict(stage=stage,id=eid,revision=key.rsplit('/',1)[1],first=event['first'],
                    accepted_cycles=[v['cycle'] for v in event['accepted']],output_handshake_cycles=[v['cycle'] for v in event['outputs']],
                    accepted_beats=len(event['accepted']),leaked_beats=len(event['outputs']),
                    actual_property_evidence=[v for v in measure['obligation_assertion_evidence'] if v['evidence']==eid]))
        row=dict(stage=stage,ordinary_accept=measure['ordinary_accept'],historical_accept=measure['historical_accept'],
            public_detected=len(set(measure['public_targets'])&set(measure['detected_ids'])),public_total=len(measure['public_targets']),
            history_detected=len(set(measure['historical_targets'])&set(measure['detected_ids'])),history_total=len(measure['historical_targets']),
            target_triggered=len(set(measure['public_targets']+measure['historical_targets'])&set(measure['triggered_ids'])),
            false_positives=len(measure['false_positives']),lost=len(measure['lost']),critical_unknown=len(measure['critical_unknown']),
            compiled=sum(j['result']['compile_status']=='passed' for j in jobs),executed=sum(j['result']['execution_status']=='completed' for j in jobs))
        stage_rows.append(row)
    if outcome['status']=='stop_both_accept_no_discrimination':
        ck('both rules accepted same proposal',len(stage_rows)==1 and stage_rows[0]['ordinary_accept'] and stage_rows[0]['historical_accept'])
        ck('stop without second call',cost['model_calls']==1 and not(run/'recovery').exists())
        ck('no freeze or independent selection',not(run/'frozen').exists() and not(run/'independent').exists() and outcome['independent'] is None)
        ck('no conditional recovery invented',outcome['conditional_recovery_numerator']==outcome['conditional_recovery_denominator']==0 and not outcome['real_chain_success'])
        terminal=s.read(run/'terminal_versions.json');candidate=s.read(run/'shared/model_call/candidate.json')
        ck('both accepted active candidate identical',terminal['O']==terminal['H']==candidate)
    s.dump(out/'stage_results.json',stage_rows);s.dump(out/'transaction_traces.json',traces)
    s.dump(out/'cost.json',cost)
    metrics=dict(new_complete_model_versions=sum(x['historical_accept'] for x in stage_rows),
        real_extra_rejections=int(outcome['first'] is not None and outcome['first']['branch']=='history_once'),
        conditional_recovery=dict(numerator=outcome['conditional_recovery_numerator'],denominator=outcome['conditional_recovery_denominator'],estimate=None if not outcome['conditional_recovery_denominator'] else outcome['conditional_recovery_numerator']/outcome['conditional_recovery_denominator']),
        new_independent_tests=0 if outcome['independent'] is None else 32,model_calls=cost['model_calls'],unused_call_cap=2-cost['model_calls'],
        unused_cap_transferable=False,status=outcome['status'],H_R_equivalent=True,tasks2_3_expanded=False)
    s.dump(out/'milestones.json',metrics)
    lines=['# research189 受限先导实跑结果','',f'终态：**{outcome["status"]}**。', '',
        '|阶段|普通接受|历史接受|公共检出|历史检出|目标触发|误报|丢失旧检出|关键unknown|编译/执行|',
        '|---|---|---|---|---|---|---|---|---|---|']
    for v in stage_rows:
        lines.append(f"|{v['stage']}|{v['ordinary_accept']}|{v['historical_accept']}|{v['public_detected']}/{v['public_total']}|{v['history_detected']}/{v['history_total']}|{v['target_triggered']}|{v['false_positives']}|{v['lost']}|{v['critical_unknown']}|{v['compiled']}/12，{v['executed']}/12|")
    if outcome['status']=='stop_both_accept_no_discrimination':
        lines+=['','**首轮真实模型版本通过相同公共与历史检查；未出现区分机会，按协议停止。** 未使用第二次额度，没有恢复调用，也没有冻结或新独立测试。本协议只允许完整恢复后做独立验收，不能把双方直接接受追改为恢复成功。',
            '', '模型保留first_stalled，并新增ready_first_oversize：在首拍就绪且已完成输入长度超过DEPTH时禁止first_present。实际目标点触发并报警。ready_first_legal的前件已包含其后件条件，因此是冗余性质，不作为额外保护或机制收益。全部性质直接来自真实响应，没有人工改写。',
            '', 'Depth16/32各有首拍就绪与首拍背压见证，公共2/2、历史2/2。Depth8保留为无目标曝光控制，不能计作目标通过。每个输入帧只计一个证据，泄漏多个拍、同一根因的参数变体不计多个独立Bug。固定版无对应违例，合法前后帧由原始端口事务参考核验。']
    lines+=['',f"实际成本：模型{cost['model_calls']}次；输入/输出tokens {cost['prompt_tokens']} / {cost['completion_tokens']}；原生编译{cost['native_compiles']}次、执行{cost['native_executions']}次；编译{cost['compile_seconds']:.3f}秒、执行{cost['execute_seconds']:.3f}秒；形式化0次。用量来自服务终态，不用预算预留替代。",
        '',f"结果审计{len(checks)}项通过，旧封存及research187/188结果保持不变。",
        '', f"里程碑：新增完整开发接受版本{metrics['new_complete_model_versions']}；真实额外拒绝{metrics['real_extra_rejections']}；条件恢复{metrics['conditional_recovery']['numerator']}/{metrics['conditional_recovery']['denominator']}（分母0时不可估计）；新独立验收{metrics['new_independent_tests']}。",
        '', '任务1：本先导已按协议完成，仍未获得前瞻性的额外拒绝→恢复→独立通过链；不能用直接接受证明历史门控的增量收益。不追加调用寻找退化，未用额度不自动转作其他用途。任务2、3未扩展。H/R等价，576次搜索负结果保持。',
        '', '若要验收这个直接接受版本，须另立保持断言不变的本地独立验收协议；不追改本先导。未做独立测试前只能报告开发范围接受，不宣称独立通过、全局保护或形式化证明。',
        '', '本地结果复核（无模型、无仿真）：','```powershell',f'wsl -- python3 scripts/research189_result_audit.py --prepared {s.rel(prep)} --run {s.rel(run)} --out deliverables/research189_reaudit','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 真实提案与事务轨迹','', '以下均来自本次真实响应和原生执行。','', '初始部分集合：','```json',json.dumps(initial,ensure_ascii=False,indent=2),'```']
    for v in stage_rows:
        c=s.read(run/v['stage']/'model_call/model_edit.json');trace+=['',v['stage']+'模型原始结果：','```json',json.dumps(c,ensure_ascii=False,indent=2),'```']
    trace+=['','逐事务采样、接受及握手周期见 transaction_traces.json；没有新独立结果，不拼接旧独立测试。']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    files=[f for f in run.rglob('*') if f.is_file() and 'obj_dir' not in f.parts]
    files += [Path(__file__),prep/'seal.json',prep/'source_bindings.json']
    s.dump(out/'source_bindings.json',{s.rel(f):s.sha(f) for f in sorted(files)})
    s.dump(out/'seal.json',{s.rel(f):s.sha(f) for f in sorted(out.rglob('*')) if f.is_file()})
    b.verify_manifest(out/'seal.json');print('AUDITED189',json.dumps(metrics),flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--prepared',type=Path,required=True);cli.add_argument('--run',type=Path,required=True);cli.add_argument('--out',type=Path,required=True)
    args=cli.parse_args();audit(args.prepared.resolve(),args.run.resolve(),args.out.resolve())
