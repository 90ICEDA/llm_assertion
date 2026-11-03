"""Reuse raw native audit; distinguish the third total pilot transmission."""
import argparse
from pathlib import Path
import research68_result_audit as previous
import research69_deadline_pilot as run


def precheck(out):
    out.mkdir(parents=True,exist_ok=False);checks=[];count=0
    prep=run.prior.PREP;candidate=run.read(prep/'shared_initial.json')
    with run.prior.base.extension.installed():
        for name,filename in (('common','common_cases.json'),('search','search_cases.json')):
            count+=previous.raw_replay(prep/'core/native'/name,run.read(prep/filename),candidate,checks)
    run.dump(out/'audit.json',dict(passed=True,native_records_recomputed=count,checks=checks,new_native_calls=0,model_calls=0,
        scope='Existing development records validate the raw-audit path only; no candidate or independent success is inferred.'))
    print('PRECHECK',count,'native records',flush=True)


def audit(prep,root,out):
    run.verify(prep)
    previous.audit(prep,root,out)
    outcome=run.read(root/'outcome.json')
    assert outcome['prior_calls']==2 and outcome['actual_new_calls']<=1
    extra=[]
    if outcome['accepted']:
        candidate=run.read(root/'core/frozen_candidate.json')
        frozen=run.read(root/'core/freeze.json')
        assert frozen['candidate_sha256']==run.prior.base.loop.sha(candidate)
        extra.append('accepted candidate hash equals freeze manifest')
    if (root/'independent/summary.json').exists():
        from research35_campaign import join_results,metrics
        from research29_drain import assess
        split=run.read(root/'independent/split.json')
        boundary=run.read(root/'independent/boundary/result.json')
        drain=run.read(root/'independent/drain/result.json')
        combined=join_results([boundary,drain])
        for row in combined['group']['ledger']:row['split']='independent_test'
        actual=metrics(combined)
        summary=run.read(root/'independent/summary.json')
        assert actual==summary['metrics']
        check=assess(root/'independent/drain',split['drain_cases'],drain)
        assert check==run.read(root/'independent/drain_assessment.json')
        passed=combined['healthy'] and check['passed'] and all(
            v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown'))
            for v in actual['obligations'].values())
        assert passed==summary['all_five_pass_on_first_attributed_evidence']==outcome['pilot_passed']
        assert (root/'core/freeze.json').stat().st_mtime_ns < (root/'independent/split.json').stat().st_mtime_ns
        extra.extend(['independent obligation metrics recomputed','drain exposure reassessed',
                      'complete independent decision recomputed','freeze precedes test generation'])
    run.dump(out/'additional_audit.json',dict(passed=True,checks=extra,
        source_sha256=run.prior.base.search.digest(Path(__file__)),new_native_calls=0,model_calls=0))
    report=out/'SUMMARY.md';text=report.read_text(encoding='utf-8')
    text=text.replace('# research68：服务诊断与先导续接','# research69：单次延长时限诊断与先导')
    text=text.replace('原先导累计2/3','原先导累计3/3')
    text=text.replace('scripts/research68_result_audit.py --prepared',
                      'scripts/research69_result_audit.py audit --prepared')
    text=text.replace('deliverables/research68_audit_NEW','deliverables/research69_audit_NEW')
    text+='\n本轮按单独批准将最后1次额度用于300秒诊断；消息、模型和采样不变，传输源码仅一处180→300改动。没有自动重试。research67、68失败均保留，辅助改动不计为机制收益。\n'
    report.write_text(text,encoding='utf-8')
    run.dump(out/'accounting.json',dict(prior_calls=2,new_calls=outcome['actual_new_calls'],
        total_calls=2+outcome['actual_new_calls'],authorized_cap=3,remaining=1-outcome['actual_new_calls']))
    if (root/'core/v0/decision.json').exists():
        b=run.prior.base
        decision=run.read(root/'core/v0/decision.json')
        target=run.read(root/'core/v0/target_gate.json')
        initial=run.read(run.prior.PREP/'shared_initial.json')
        candidate=run.read(root/'core/v0/model_call/candidate.json')
        before=b.loop.inspect(b.campaign.baseline(run.prior.PREP,'search')['group']['ledger'])
        rows=target.get('target_gate',{}).get('target_rows',[])
        examples=[dict(native_check=r,prior_evidence=before['rows'][r['evidence_id']]) for r in rows]
        run.dump(out/'case_trace.json',dict(initial=initial,real_model_candidate=candidate,
            examples=examples,history_counts=decision.get('history',{}).get('counts'),
            accepted=decision['accepted'],independent_pass=outcome['pilot_passed']))
        lines=['# research69 实际修改轨迹','',
            '本轮真实模型仅替换 a4；其他四条性质保持原样。结构化 AST 只做语法组装，没有人工修改谓词。','',
            '原性质：','```systemverilog',next(a['property'] for a in initial['assertions'] if a['id']=='a4'),'```','',
            '模型新性质：','```systemverilog',next(a['property'] for a in candidate['assertions'] if a['id']=='a4'),'```','',
            '|证据|前件周期|检查周期|新性质触发/失败|正确侧触发|',
            '|---|---|---|---|---|']
        for r in rows:
            a=r['edited_assertion']
            lines.append(f"|{r['evidence_id']}|{r['native_antecedent_cycle']}|{r['check_cycle']}|{a['trigger']}/{a['failed']}|{r['correct_side_trigger']}|")
        lines+=['','开发门控原始记录：'+str(root/'core/v0/target_native'),
            '','历史回放：'+str(root/'core/v0/history_native'),
            '',f"完整接受={decision['accepted']}；新独立验收={outcome['pilot_passed']}。每个样本对应的独立义务判断和旧断言状态保存在 case_trace.json，完整波形在原生目录的 wave.vcd。",
            '', '解除边界属于公共已知缺口；持续背压见证来自契约搜索，虽未由本轮公共反馈曝光，但已经是历史已知人工故障。其他搜索方法也找到同一去重缺口，因此本例不证明契约独有收益。',
            '', '本提案同时通过普通目标门控与历史门控，后者没有额外拒绝它。历史保护保持不等于防退化机制具有已证实的增量收益。模型接口、组件生成和传输调整均属于公共辅助措施。',
            '', '独立测试仅用于冻结后验收，不反馈或选择候选；后续归因 unknown 保留。结论限实际 FIFO RTL 加人工故障的有限仿真范围，不能当作原始历史缺陷复现、全局无退化或形式化证明。']
        (out/'CASE_TRACE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('precheck','audit'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--run',type=Path)
    a=p.parse_args()
    if a.action=='precheck':precheck(a.out.resolve())
    else:audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
