"""Audit research169 terminal real run without calls or acceptance-rule changes."""
import argparse
from collections import Counter
import re
from pathlib import Path
import research169_adapter_parameter_scope as s

P=s.q.ROOT/'deliverables/research169_scope_controller_prepare_20261028_r02'
RUN=s.q.ROOT/'deliverables/research169_adapter_run_20261028_r01'


def main(out):
    s.c.verify(P);s.c.verify(s.OLD)
    checks,check=s.check_list();result=s.read(RUN/'shared/model_call/result.json')
    candidate=s.read(RUN/'shared/model_call/candidate.json');raw=s.read(RUN/'shared/model_call/model_edit.json')
    ev=s.read(RUN/'shared/evaluation.json');outcome=s.read(RUN/'outcome.json');cost=s.read(RUN/'cost.json')
    scenarios=s.read(s.c.P/'scenarios.json');protected=s.read(P/'protected.json')
    check('actual request exactly sealed',s.read(RUN/'shared/model_call/request.json')==s.read(P/'request.preview.json'))
    check('real requested model',result['actual_server_model']=='deepseek/deepseek-v3-0324' and result['stream_terminal_received'])
    check('original model predicates retained',candidate==raw['assertions']==s.c.adapt(raw))
    check('interface accepted',result['candidate_status']=='model_expressions_preserved_no_semantic_repair')
    check('native verdict independently replayable',s.c.measure(candidate,RUN/'shared/native',scenarios,protected)==ev)
    for rev in ('before','after'):
        n=s.read(RUN/'shared/native'/rev/'result.json')
        check('native compile and execution '+rev,n['compile_status']=='passed' and n['execution_status']=='completed')
        check('original RTL source '+rev,s.q.sha(s.c.P/'rtl'/rev/'axis_adapter.v')==s.read(P/'code_bindings.json').get(s.q.old.rel(s.c.P/'rtl'/rev/'axis_adapter.v'),s.q.sha(s.c.P/'rtl'/rev/'axis_adapter.v')))
    check('33 development scenarios',len(scenarios)==33)
    check('public8 history20 targets',len(ev['public_targets'])==8 and len(ev['history_targets'])==20)
    check('all targets detected and triggered',not any(ev[k] for k in ('public_missed','history_missed','public_untriggered','history_untriggered')))
    check('old detections remain in proposal',not ev['lost'])
    check('68 extra before cycles zero after',len(ev['false_before'])==68 and not ev['false_after'])
    check('no execution/oracle unknown in frozen gate',not ev['unknown'])
    check('both reject under unchanged rule',not ev['ordinary'] and not ev['history'] and outcome['status']=='stop_ordinary_rejects')
    check('only shared call used',len(list(RUN.rglob('attempt.json')))==1 and len(s.read(RUN/'budget_ledger.json')['reserved_calls'])==1)
    check('no recovery or independent started',not (RUN/'recovery').exists() and not (RUN/'independent').exists() and not (RUN/'terminal_freeze.json').exists())
    check('no real recovery opportunity',outcome['conditional_recovery_denominator']==outcome['conditional_recovery_numerator']==0)
    baseline=s.read(P/'initial.json');versions=s.read(RUN/'terminal_versions.json')
    check('both previous versions retained',versions==dict(O=baseline,H=baseline))
    check('cost reconciled',cost==s.c.costs(RUN,'real') and cost['model_calls']==1 and cost['native_compiles']==cost['native_executions']==2)
    check('tokens reconciled',cost['prompt_tokens']==result['prompt_tokens']==11294 and cost['completion_tokens']==result['completion_tokens']==649)
    g=s.read(RUN/'authorization.json');s.c.validate_grant(g,s.q.sha(P/'seal.json'),s.q.old.rel(RUN))
    check('within grant',cost['model_calls']<=g['authorized_calls']==2)
    # Post-run timing attribution, never changes frozen verdict or feeds model.
    n=s.read(RUN/'shared/native/before/result.json');trace=ev['evidence']['before']['trace']
    oracle=ev['evidence']['before']['oracle'];targets=set(ev['public_targets']+ev['history_targets'])
    failures={}
    for f in n['failures']:
        cycle=int(re.fullmatch(r'cycle=(\d+)',f['detail'])[1]);failures.setdefault(cycle,[]).append(f['id'])
    rows=[]
    for cycle in ev['false_before']:
        v=trace[cycle]
        following=next((x for x in trace[cycle+1:] if x['sid']==v['sid'] and x['mv'] and x['mr']),None)
        same=bool(following and all(x['sid']==v['sid'] and x['mv'] and not x['rst'] and
            all(x[k]==v[k] for k in ('md','mk','ml')) for x in trace[cycle:following['cycle']+1]))
        rows.append(dict(cycle=cycle,sid=v['sid'],sample=v,assertions=failures[cycle],
            handshake=bool(v['mv'] and v['mr']),reference_checks=[x for x in oracle['checks'] if x['cycle']==cycle],
            next_output_cycle=following['cycle'] if following else None,same_output_stable_until_acceptance=same,
            next_output_is_known_target=bool(following and following['cycle'] in targets),
            sealed_classification='false_before: failure outside target cycle set',
            semantic_false_positive='not independently established by absence of a transferred-output mask check'))
    check('all extra alarms on stalled zero keep',all(x['sample']['mv']==1 and x['sample']['mr']==0 and x['sample']['mk']==0 for x in rows))
    check('only extra property alarms on these cycles',all(x['assertions']==['keep_never_zero_when_valid'] for x in rows))
    attribution=dict(cycles=rows,all_stalled=True,linked_to_later_target=sum(x['same_output_stable_until_acceptance'] and x['next_output_is_known_target'] for x in rows),
        note='Diagnostic association only. Frozen O/H rejection unchanged. Early alarms on buggy stalled output cannot automatically be equated with false alarms on legal behavior. No new rule, model request or independent test used.')
    report=dict(complete_acceptance=dict(numerator=0,denominator=1),public_detected=8,public_exposed=8,history_detected=20,history_exposed=20,
        prior_protection_lost=0,extra_historical_rejections=0,conditional_recovery=dict(numerator=0,denominator=0,rate=None),
        sealed_false_before=68,false_after=0,legal_false_positive_count='not established for the68 non-handshake alarms',
        gate_unknown_count=0,posthoc_attribution=attribution['linked_to_later_target'],independent_status='not_started',cost=cost)
    out.mkdir(parents=True,exist_ok=False)
    s.dump(out/'checks.json',checks);s.dump(out/'metrics.json',report);s.dump(out/'alarm_attribution.json',attribution)
    s.dump(out/'failures_by_assertion.json',dict(Counter(x['id'] for x in n['failures'])))
    (out/'SUMMARY.md').write_text(f'''# research169 真实先导：普通规则拒绝，按协议停止

执行1次已授权DeepSeek V3-0324调用，接口通过，模型6条性质保持原样。原始前后RTL各编译/执行1次。没有第二次调用、恢复、接受冻结或新独立测试；剩余1次仅限条件恢复，不自动改作重试。

| 指标 | 实际结果 |
| --- | --- |
| 新完整接受版本 | 0/1真实提案 |
| 公共目标检出/曝光 | 8/8采样点，必要触发通过 |
| 历史目标检出/曝光 | 20/20采样点，必要触发通过 |
| 原基线12个历史检出丢失 | 0 |
| 封存规则的额外报警 | buggy68个非目标周期；fixed0 |
| 原生执行/参考判定关键unknown | 0 |
| 普通/历史决定 | 均拒绝；没有额外历史拒绝机会 |
| 条件恢复 | 0/0，不可估计 |
| 活动版本 | O/H均保留旧部分基线 |
| 新独立验收 | 未启动 |

## 拒绝原因与判定范围

真实提案新增 `keep_never_zero_when_valid`：`m_axis_tvalid |-> m_axis_tkeep != {{M_KEEP_WIDTH{{1'b0}}}}`。它在输出已呈现但背压尚未解除时也检查KEEP。封存参考目标按握手输出周期记录；普通规则将目标周期集合以外的断言报警记为false_before，因此拒绝。

68个额外报警全部来自该性质，均为valid=1、ready=0、keep=0，发生在buggy RTL。后续逐周期关联中，{attribution['linked_to_later_target']}/68个报警与同一保持中的输出随后进入已知目标违例周期对应。fixed RTL没有报警。

因此应区分“封存规则记为68个误报”与“独立确认68次合法行为误报”：后者尚未成立。这里可能包含已知错误输出在握手前的提前检出；不能只因不在目标周期集合就宣称模型过宽，也不能据此追改本轮接受决定。详细采样与后续握手关系在alarm_attribution.json中，均为开发数据的事后诊断。

本轮不能验证增加历史检查的作用，也不能计新恢复成功；H/R等价限制不变。research167失败及research169此前本地诊断保持独立记录。

## 成本与下一步

实际模型1次，输入11294、输出649 tokens；原生编译2次、执行2次；编译{cost['compile_seconds']:.3f}s、执行{cost['execute_seconds']:.3f}s；形式化0次。{len(checks)}项结果复核通过。

下一步若继续，先本地审计非握手输出周期的规格适用性和参考模型标注，区分合法误报、提前检出与unknown，再决定是否需要新的协议。保持本轮拒绝，不追加模型调用或删掉性质制造通过。

只读复核源记录的命令（写入新的审计目录；不调用模型或仿真）：
```powershell
wsl -- python3 scripts/research170_adapter_real_audit.py --out deliverables/research170_adapter_real_audit_repeat
```

源记录：deliverables/research169_adapter_run_20261028_r01/；封存请求：deliverables/research169_scope_controller_prepare_20261028_r02/request.preview.json。
''',encoding='utf-8')
    sources=[p for p in RUN.rglob('*') if p.is_file() and 'obj_dir' not in p.parts]+[Path(__file__),P/'seal.json']
    s.dump(out/'source_bindings.json',{s.q.old.rel(p):s.q.sha(p) for p in sources});s.seal_files(out)
    s.c.verify(P);print('AUDITED170',len(checks),'checks; extra-reject0; recovery0/0; linked',attribution['linked_to_later_target'],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args();main(a.out.resolve())
