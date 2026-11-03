"""Read-only audit of the bounded research172 real pilot. Never calls a model."""
import argparse
from collections import Counter
import json
from pathlib import Path
import research172_applicability_gate as g

q=g.q
PREP=q.ROOT/'deliverables/research172_applicability_prepare_20261028_r02'
RUN=q.ROOT/'deliverables/research172_adapter_run_20261028_r01'


def main(out):
    g.c.verify(PREP);g.s.c.verify(g.OLD);checks,check=g.s.check_list()
    result=q.read(RUN/'shared/model_call/result.json');raw=q.read(RUN/'shared/model_call/model_edit.json')
    candidate=q.read(RUN/'shared/model_call/candidate.json');evaluation=q.read(RUN/'shared/evaluation.json')
    outcome=q.read(RUN/'outcome.json');decision=q.read(RUN/'shared_decision.json');cost=q.read(RUN/'cost.json')
    check('real complete requested model',result['status']=='response_received' and result['stream_terminal_received'] and result['actual_server_model']=='deepseek/deepseek-v3-0324')
    check('exact sealed request used',q.read(RUN/'shared/model_call/request.json')==q.read(PREP/'request.preview.json'))
    check('model predicates unchanged',candidate==raw['assertions']==g.c.adapt(raw))
    check('new version differs from partial baseline',g.c.signature(candidate)!=g.c.signature(q.read(PREP/'initial.json')))
    scenarios=q.read(g.c.P/'scenarios.json');protected=q.read(PREP/'protected.json')
    reproduced=g.measure(candidate,RUN/'shared/native',scenarios,protected)
    # JSON object cycle keys are strings on disk, integers in the live table.
    check('new gate reproduces saved verdict exactly',json.loads(json.dumps(reproduced))==evaluation)
    check('both policies accept',evaluation['ordinary'] and evaluation['history'])
    check('public8 history20 exposed',len(evaluation['public_targets'])==8 and len(evaluation['history_targets'])==20)
    for field in ('public_missed','history_missed','public_untriggered','history_untriggered','false_before','false_after','unknown','lost'):
        check('none '+field,not evaluation[field])
    versions=q.read(RUN/'terminal_versions.json')
    check('same real proposal becomes both active versions',versions==dict(O=candidate,H=candidate))
    candidate_hash=g.c.digest(candidate)
    check('active hashes agree',decision['active_hashes']==dict(O=candidate_hash,H=candidate_hash))
    check('correct terminal branch',outcome['status']=='stop_both_accept_no_discrimination')
    check('no conditional opportunity or recovery',outcome['conditional_recovery_numerator']==outcome['conditional_recovery_denominator']==0 and not outcome['full_recovery_accepted'])
    check('one physical call no second branch',len(list(RUN.rglob('attempt.json')))==1 and not (RUN/'recovery').exists())
    check('independent not started',outcome['independent'] is None and not (RUN/'independent').exists() and not (RUN/'terminal_freeze.json').exists())
    check('no chain-success inflation',not outcome['real_chain_success'] and not outcome['automatic_expansion'])
    check('actual costs reconciled',cost==g.c.costs(RUN,'real') and cost['model_calls']==1 and cost['native_compiles']==cost['native_executions']==2)
    check('actual tokens reconciled',result['usage_available'] and cost['prompt_tokens']==result['prompt_tokens']==11384 and cost['completion_tokens']==result['completion_tokens']==648)
    grant=q.read(RUN/'authorization.json');g.c.validate_grant(grant,q.sha(PREP/'seal.json'),q.old.rel(RUN))
    check('within scoped two-call authorization',cost['model_calls']<=grant['authorized_calls']==2)
    for rev in ('before','after'):
        n=q.read(RUN/'shared/native'/rev/'result.json')
        check('native completed '+rev,n['compile_status']=='passed' and n['execution_status']=='completed')
    coverage=Counter(ob for r in evaluation['obligation_evaluation']['before']['target_coverage'] for ob in r['obligations'])
    check('repair obligation exposure both types',coverage==Counter(nonfinal_keep=12,final_nonempty=16))
    before=evaluation['obligation_evaluation']['before']
    after=evaluation['obligation_evaluation']['after']
    mapping=[]
    for a in candidate:
        mapping.append(dict(label=a['label'],obligations=a['obligations'],
            before_trigger_cycles=before['own_effective_triggers'][a['label']],after_trigger_cycles=after['own_effective_triggers'][a['label']],
            before_failure_cycles=[r['cycle'] for r in before['alarms'] if r['assertion']==a['label']],
            after_failure_cycles=[r['cycle'] for r in after['alarms'] if r['assertion']==a['label']]))
    check('each property triggered natively observed',all(x['before_trigger_cycles'] and x['after_trigger_cycles'] for x in mapping))
    # Terminal hash is an audit identifier, not a retroactive independent-test freeze.
    metrics=dict(case='original axis_adapter historical TKEEP repair; registered8to32 only',
        unique_new_development_accepted_versions=1,accepted_per_generated=dict(numerator=1,denominator=1),
        public=dict(exposed=8,detected=8),history=dict(exposed=20,detected=20),target_obligations=dict(coverage),
        prior_detection_points_retained=len(protected),false_positives=0,critical_unknown=0,
        extra_history_rejections=0,conditional_recovery=dict(numerator=0,denominator=0,rate=None),
        independent_tests=0,complete_recovery_chain=False,accepted_candidate_hash=candidate_hash,
        stall_target_exposure=0,scope='Finite development evidence only. No cross-case stability, global protection or formal proof claim.',cost=cost)
    out.mkdir(parents=True,exist_ok=False)
    q.dump(out/'metrics.json',metrics);q.dump(out/'checks.json',checks);q.dump(out/'obligation_mapping.json',mapping)
    q.dump(out/'accepted_candidate_reference.json',dict(candidate=candidate,hash=candidate_hash,
        origin=q.old.rel(RUN/'shared/model_call/model_edit.json'),status='accepted_on_development_only_not_independently_tested'))
    tb=(RUN/'shared/native/after/tb.sv').read_text()
    lines=[line for line in tb.splitlines() if ': assert property ' in line]
    assert len(lines)==len(candidate)
    (out/'accepted_assertion_excerpt.sv').write_text('// Exact lines from actually executed tb.sv. Requires that sealed host/parameter context.\n'+'\n'.join(lines)+'\n')
    (out/'SUMMARY.md').write_text(f'''# research172 受限先导结果：两规则同时接受，按协议停止

1次真实DeepSeek V3-0324调用产生1个新的开发验收通过版本。共享提案原样在原始前后RTL编译执行，普通和历史规则均接受；没有额外拒绝机会，因此没有第二次调用、恢复或独立测试。没有修改请求或追加重试。

| 指标 | 本轮实际结果 |
| --- | --- |
| 新真实生成版本完整开发接受 | 1/1提案（O/H共享同一版本，不计2次成功） |
| 公共目标检出/曝光 | 8/8采样点 |
| 历史目标检出/曝光 | 20/20采样点 |
| 修复义务曝光 | 非尾拍满KEEP12点；尾拍非空KEEP16点 |
| 必要触发 | 目标周期通过；5条性质在前后RTL均有触发记录 |
| 旧保护保持 | 原基线12个历史检出点均保留 |
| 误报/关键unknown | 0/0 |
| 历史额外拒绝 | 0 |
| 条件恢复 | 0/0，不可估计 |
| 新独立验收 | 0，按本协议未启动 |

## 真实生成轨迹

原部分基线只保护非尾拍KEEP以及背压保持，遗漏公共尾拍目标。模型本次返回5条性质：保留非尾拍满KEEP检查，增加尾拍非零KEEP检查，并给出valid、整体载荷和KEEP的跨周期保持。模型使用已绑定M_KEEP_WIDTH，未人工替换参数名或性质。可执行性质原文见accepted_assertion_excerpt.sv；完整宿主、原始请求/响应、工具版本、编译和执行日志位于运行目录。

原生参考回放的28个目标采样均被检出，历史12点保护未丢失。背压保持只有合法触发/无误报证据，本批没有背压违例目标曝光，不能声称所有义务的故障保护均已完整验证。

## 机制结论与停止条件

本次取得新的真实开发接受版本，但没有“普通接受、历史拒绝”的区分机会。不能据此声称历史门控产生额外收益或恢复成功。条件恢复仍0/0；H/R等价限制保持。两规则同时接受即停止，因此不为本次接受版本追加独立测试；剩余1次仅限本协议条件恢复，不能改作重试或新用途。

research167/169失败、research171审计及research172本地重判记录保持原样。该结果不追改旧实验，也不等于新独立验收、全局无退化或形式化证明。

## 成本与复核

实际模型1次，输入11384、输出648 tokens；原生编译2次、执行2次；编译{cost['compile_seconds']:.3f}s、执行{cost['execute_seconds']:.3f}s；形式化0次。{len(checks)}项结果复核通过。

只读复核命令（写入新的审计目录，不发请求或运行仿真）：
```powershell
wsl -- python3 scripts/research173_pilot_result_audit.py --out deliverables/research173_pilot_result_audit_repeat
```

运行产物：deliverables/research172_adapter_run_20261028_r01/。
下一步如继续，应先本地评估是否还有实质性的候选保护取舍，再决定新前瞻协议；不重复调用同一成功案例以寻求区分机会。
''',encoding='utf-8')
    sources=[p for p in RUN.rglob('*') if p.is_file() and 'obj_dir' not in p.parts]+[Path(__file__),PREP/'seal.json']
    q.dump(out/'source_bindings.json',{q.old.rel(p):q.sha(p) for p in sources});g.s.seal_files(out)
    g.c.verify(PREP)
    print('AUDITED173',len(checks),'checks; development accepted1; extra rejection0; recovery0/0; independent0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args();main(a.out.resolve())
