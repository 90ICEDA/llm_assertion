"""Read-only research167 real pilot audit; no model calls or native execution."""
import argparse
import json
import re
from pathlib import Path
import research167_adapter_controller as c

q=c.q
P=q.ROOT/'deliverables/research167_adapter_controller_prepare_20261028_r02'
RUN=q.ROOT/'deliverables/research167_adapter_run_20261028_r01'


def main(out):
    c.verify(P)
    checks=[]
    def check(name,value):
        checks.append(dict(check=name,passed=bool(value)))
        assert value,name
    result=q.read(RUN/'shared/model_call/result.json')
    response=q.read(RUN/'shared/model_call/model_edit.json')
    outcome=q.read(RUN/'outcome.json');cost=q.read(RUN/'cost.json')
    ledger=q.read(RUN/'budget_ledger.json');decision=q.read(RUN/'shared_decision.json')
    check('actual request matches sealed request',q.read(RUN/'shared/model_call/request.json')==q.read(P/'request.preview.json'))
    check('server confirmed requested model',result['actual_server_model']=='deepseek/deepseek-v3-0324')
    check('complete real response',result['status']=='response_received' and result['stream_terminal_received'])
    check('usage available',result['usage_available'] and result['prompt_tokens']==11013 and result['completion_tokens']==521)
    check('interface rejection recorded',result['candidate_status']=='interface_rejected' and result['candidate_error']['detail']=='non_interface_identifier')
    try:c.adapt(response)
    except ValueError as e:check('reproduced same interface rejection',str(e)=='non_interface_identifier')
    else:raise AssertionError('sealed frontend unexpectedly accepts')
    identifiers=[]
    for a in response['assertions']:
        for field in ('antecedent','consequent'):
            text=re.sub(r"\d+'[hHbBdD][0-9a-fA-F_]+",'0',a[field])
            unknown=set(re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*',text))-q.SIGNALS-{'$stable','$past'}
            if unknown:identifiers.append(dict(label=a['label'],field=field,expression=a[field],unavailable_identifiers=sorted(unknown)))
    check('exact rejection cause two width references',len(identifiers)==2 and all(x['unavailable_identifiers']==['M_KEEP_WIDTH'] for x in identifiers))
    initial=q.read(P/'initial.json');versions=q.read(RUN/'terminal_versions.json')
    for arm in ('O','H'):
        check(arm+' original baseline remains active',versions[arm]==initial and decision['active_hashes'][arm]==c.digest(initial))
    protected=q.read(P/'protected.json')
    check('12 historical detections retained by unchanged version',len(protected)==12 and decision['retained_historical_detection_ids']==protected)
    check('native gates unmeasured',not decision['measured'] and not outcome['first']['measured'])
    check('terminal stop interface branch',outcome['status']=='stop_interface_or_repeat')
    check('no conditional opportunity',outcome['conditional_recovery_denominator']==0)
    check('no recovery accepted',not outcome['full_recovery_accepted'] and outcome['conditional_recovery_numerator']==0)
    check('one physical submission',len(list(RUN.rglob('attempt.json')))==1 and len(ledger['reserved_calls'])==1)
    check('no native reservation or execution',ledger['native_stages']==[] and not list(RUN.rglob('compile.json')) and not list(RUN.rglob('execute.json')))
    check('no recovery or independent inputs',not (RUN/'recovery').exists() and not (RUN/'independent').exists())
    check('no accepted freeze',not (RUN/'terminal_freeze.json').exists())
    check('cost reconciles with transport',c.costs(RUN,'real')==cost and cost['model_calls']==1)
    check('no automatic expansion or false chain claim',not outcome['automatic_expansion'] and not outcome['real_chain_success'])
    g=q.read(RUN/'authorization.json');c.validate_grant(g,q.sha(P/'seal.json'),q.old.rel(RUN))
    check('within explicitly authorized bound',cost['model_calls']<=g['authorized_calls'])
    body=json.loads(q.read(P/'request.preview.json')['messages'][1]['content'])
    diagnosis=dict(cause='Two proposed consequents use bare M_KEEP_WIDTH, outside sealed identifier interface and undeclared in assertion testbench scope.',
        references=identifiers,request_fields=list(body),
        scope='M_KEEP_WIDTH occurs in supplied DUT RTL as a parameter. This does not put it in the assertion-host module scope.',
        change_applied=False,semantic_correctness='not_evaluated',syntax_compile='not_attempted',tool_support='not_evaluated',
        future_option='If pursuing a new protocol, first locally validate explicit parameter bindings in the assertion host, or clarify the permitted fixed-width literal interface. Re-seal before any new model call. Do not substitute the current response or reclassify this run.',
        unused_call='One unspent call is conditional recovery only. With no qualified opportunity this run is terminal; not available for interface retry.')
    metrics=dict(model_submissions=1,complete_acceptance=dict(numerator=0,denominator=1),
        native_comparable_proposals=0,extra_historical_rejections=0,
        conditional_recovery=dict(numerator=0,denominator=0,rate=None,status='not_estimable'),
        new_independent_runs=0,old_baseline_unchanged=True,prior_confirmed_detection_points=12,
        independent_result='not_started',history_replay='not_started',cost=cost,
        limitation='No measurement of semantic correctness or added-history effectiveness. H/R equivalence unchanged.')
    out.mkdir(parents=True,exist_ok=False)
    q.dump(out/'checks.json',checks);q.dump(out/'diagnosis.json',diagnosis);q.dump(out/'metrics.json',metrics)
    (out/'SUMMARY.md').write_text('''# research167 真实先导结果

已执行1次获批的 DeepSeek V3-0324 调用；收到完整响应，在接口阶段拒绝并按封存分支停止。未调用第二次，未人工替换参数名。

模型的两条 keep 性质使用 `{M_KEEP_WIDTH{1\'b1}}` / `{M_KEEP_WIDTH{1\'b0}}`。M_KEEP_WIDTH 是提供给模型的原始 DUT 参数，但不在封存表达式接口允许的标识符中，也未声明于断言所在的测试平台作用域。拒绝原因 `non_interface_identifier` 可本地重复核验。这是接口/作用域失败；性质语义是否正确、原生工具是否支持均未执行验证。

| 里程碑 | 本轮实际结果 |
| --- | --- |
| 新完整接受版本 | 0/1真实生成提案 |
| 普通/历史可比较的原生提案 | 0；未进入原生执行，不能把布尔false解释为原生不通过 |
| 历史额外拒绝 | 0；本轮由公共接口拒绝 |
| 旧保护保留 | O/H均保留原基线及其已有12个历史检出点，未重跑或新增确认 |
| 条件恢复 | 0/0，不可估计 |
| 历史回放、新冻结、独立验收 | 均未启动 |
| 实际成本 | 1次模型调用；输入11013、输出521 tokens；原生编译/执行0，形式化0 |

剩余1次是条件恢复额度，没有合格区分机会不能改作接口重试。当前实验已终止，不自动追加调用。H/R等价限制不变，本轮未取得增加历史检查的增量证据。

下一步如继续，应先本地核查模型可见的DUT参数与断言宿主作用域的映射，明确参数绑定或固定字面量接口，验证后重新封存。保持本轮失败，不替换本次真实响应后追认成功。

复核命令（只读源记录，写入一个新的审计目录；无远程请求）：

```powershell
wsl -- python3 scripts/research168_adapter_result_audit.py --out deliverables/research168_adapter_result_audit_repeat
```

源记录：`deliverables/research167_adapter_run_20261028_r01/`。请求/响应、成本、授权、终态与原版本均保留。
''',encoding='utf-8')
    bound=[p for p in RUN.rglob('*') if p.is_file()]+[P/'seal.json',Path(__file__)]
    q.dump(out/'source_bindings.json',{q.old.rel(p):q.sha(p) for p in bound})
    q.dump(out/'seal.json',{p.relative_to(out).as_posix():q.sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(checks=len(checks),model_calls=cost['model_calls'],status=outcome['status'],conditional_recovery='0/0'),ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args();main(a.out.resolve())
