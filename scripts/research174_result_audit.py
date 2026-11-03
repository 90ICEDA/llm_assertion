"""Read-only audit/report of the separately frozen research174 holdout.

Never compiles, calls a model, edits a candidate, or replaces failed scenes.
"""
import argparse
from collections import Counter
from pathlib import Path
import json
import research174_independent_acceptance as r

q=r.q;g=r.g


def audit(prep,run,out):
    r.verify(prep)
    # Execution artifacts have a content seal; code bindings belong to prep.
    for p,h in q.read(run/'seal.json').items():assert q.sha(run/p)==h,p
    for p,h in q.read(r.PRIOR/'source_bindings.json').items():
        assert q.sha(q.ROOT/p)==h,p
    checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        assert ok,name
    frozen=q.read(prep/'freeze.json');inputs=q.read(run/'input_freeze.json')
    candidate=q.read(prep/'candidate.json');scenes=q.read(run/'scenarios.json')
    result=q.read(run/'result.json');stats=q.read(run/'scenario_results.json')
    ev=q.read(run/'evaluation.json')
    check('selection after freeze',inputs['generated_utc']>=frozen['created_utc'])
    check('sealed prior input links',inputs['prior_freeze_hash']==q.sha(prep/'freeze.json') and inputs['prior_seal_hash']==q.sha(prep/'seal.json'))
    check('selection follows fixed seed',scenes==r.generate(q.read(prep/'protocol.json')))
    check('unchanged candidate',r.digest(candidate)==inputs['candidate_hash']==frozen['candidate_hash'])
    check('unchanged pilot',q.sha(r.PILOT/'outcome.json')==frozen['pilot_outcome_sha256'])
    check('no rerolls or model calls',result['rerolls']==0 and result['cost']['model_calls']==0)
    fresh=g.measure(candidate,run/'native',scenes)
    check('recomputed reference and gate match',json.loads(json.dumps(fresh))==ev)
    totals={};failures=[];transactions={};trigger_map={}
    for rev in ('before','after'):
        native=q.read(run/'native'/rev/'result.json');trace=q.old.trace(run/'native'/rev)
        check(rev+' native completed',native['compile_status']=='passed' and native['execution_status']=='completed')
        check(rev+' original RTL supplied',str(prep/'rtl'/rev/'axis_adapter.v') in native['compile']['argv'])
        check(rev+' unchanged executable SVA',g.q.bench(candidate,scenes).strip()==(run/'native'/rev/'tb.sv').read_text().strip())
        check(rev+' actual trace equals evidence',trace==ev['evidence'][rev]['trace'])
        check(rev+' trace complete',len(trace)==40*96)
        check(rev+' unique unseen traces',all(x['revision'][rev]['novel'] for x in stats))
        check(rev+' no false positives',not ev['false_'+rev])
        details=ev['obligation_evaluation'][rev]
        trigger_map[rev]={a['label']:dict(obligations=a['obligations'],effective_check_cycles=details['own_effective_triggers'][a['label']],
            measurement='procedural antecedent diagnostic with timing/reset alignment; not native cover proof') for a in candidate}
        totals[rev]=dict(reference_counts=details['counts'],
            property_triggers={a:len(v['effective_check_cycles']) for a,v in trigger_map[rev].items()},
            backpressure_scenarios=sum(bool(x['revision'][rev]['backpressure_cycles']) for x in stats),
            released_scenarios=sum(bool(x['revision'][rev]['release_edges']) for x in stats),
            partial_tail_outputs=sum(x['revision'][rev]['partial_final_outputs'] for x in stats),
            reset_cancel_scenarios=sum(bool(x['revision'][rev]['reset_cancellations']) for x in stats))
        transactions[rev]=g.audit.replay(trace)
        for x in stats:
            if x['stratum']=='reset_cancel':
                rr=x['revision'][rev];reset=x['configuration']['reset_at'];base=x['id']*96
                anchor=trace[base+reset-1]
                check(f'{rev} reset{ x["id"] } interrupts stalled output',bool(anchor['mv'] and not anchor['mr'] and not anchor['rst']))
                check(f'{rev} reset{ x["id"] } cancels requests and leaves quiet output',bool(rr['reset_cancellations']) and rr['postreset_no_request_no_output'])
        for ob in g.OBLIGATIONS:
            check(rev+' '+ob+' verdict accounting',sum(details['counts'][ob].values())==len(trace))
    exposure=Counter(ob for v in ev['obligation_evaluation']['before']['target_coverage'] for ob in v['obligations'])
    check('all target points directly detected and triggered',all(v['detected'] and v['triggered'] for v in ev['obligation_evaluation']['before']['target_coverage']))
    check('both KEEP classes exposed',all(exposure[o]>0 for o in g.KEEP))
    check('fixed reference passes',not ev['evidence']['after']['oracle']['failures'])
    check('no critical unknown',not ev['unknown'])
    for x in stats:
        if x['passed']:continue
        rev=x['revision']['after'];sid=x['id'];tr=ev['evidence']['after']['trace'][sid*96:(sid+1)*96]
        failures.append(dict(id=sid,issues=x['issues'],configuration=x['configuration'],
            output_samples=[{k:v[k] for k in ('cycle','phase','mv','mr','mk','ml')} for v in tr if v['mv']],
            explanation='Every output presentation coincided with ready=1. Periodic ready=0 cycles did not overlap valid=1, so no stall antecedent or release edge was exposed.'))
        check('failed scene '+str(sid)+' is exposure failure only',set(x['issues'])=={'unexposed_backpressure','unexposed_release'} and not rev['reference_failures'] and not rev['false_positive_cycles'])
        check('failed scene '+str(sid)+' all presented beats accepted',all(v['mr'] for v in tr if v['mv']))
    check('aggregate remains failed',result['status']=='failed_or_unresolved' and result['scenario_passed']==37 and len(failures)==3)
    out.mkdir(parents=True,exist_ok=False)
    q.dump(out/'audit_checks.json',checks);q.dump(out/'coverage.json',dict(target_exposure=dict(exposure),revisions=totals))
    q.dump(out/'unexposed_scenarios.json',failures);q.dump(out/'trigger_mapping.json',trigger_map)
    q.dump(out/'transaction_reference.json',transactions)
    q.dump(out/'source_bindings.json',{q.old.rel(p):q.sha(p) for p in [Path(__file__),prep/'seal.json',run/'seal.json',run/'result.json',run/'evaluation.json',run/'scenario_results.json',r.PILOT/'outcome.json']})
    lines=['# research174 独立验收复核','',
        '**整批未通过：37/40。** 两类KEEP目标33/33检出，0漏报、0误报、0关键unknown；三个合法场景没有实际背压/解除曝光，按预封存标准保持未通过。没有修改候选、补抽场景或追改research172。','',
        '|项目|实际结果|结论|','|---|---|---|',
        '|非尾拍KEEP|17个原始违例点；17检出、17必要触发|本批曝光范围通过|',
        '|尾拍非零KEEP|16个原始违例点；16检出、16必要触发|本批曝光范围通过|',
        '|合法传输|16/16无误报；14个合法部分尾拍实际输出；其中3场景缺背压/解除|按全部场景要求13/16通过|',
        '|背压与解除|37/40场景有背压；29/32非复位场景有解除；两版各230个保持检查周期|未曝光三个场景；未注入保持故障，不能报告其故障检出通过|',
        '|复位取消|8/8取消已接受请求及被背压阻塞的输出；复位后无请求且无输出|合法复位范围通过，未注入复位故障|','',
        '失败场景ID为1、7、22（13/7/6字节帧，输入间隔3，ready延迟14）。输出呈现周期恰好全部ready=1；虽然激励含周期性背压，实际事务未遇背压。具体采样见unexposed_scenarios.json。该结果是曝光不足，并非发现断言误报或目标漏报。','',
        '原始前后RTL各执行3840周期。40个实际事务轨迹均未重复开发记录，且每版内无重复；去重忽略数据值、种子与场景编号。参数固定8→32、输入KEEP禁用，未外推其他参数。',
        'SVA失败来自Verilator原生执行；触发计数来自同一执行中的前件诊断及周期/复位对齐，并非native cover或形式化证明。五条性质每版触发数分别45、32、230、230、230，见trigger_mapping.json。','',
        f'复核{len(checks)}项通过，仅说明记录和结论一致，不改变整批未通过结果。本地编译2次、执行2次，模型0次，形式化0次。',
        'research172仍是普通与历史规则同时接受后停止。本次独立验收不能改称额外拒绝或恢复成功，条件恢复仍0/0、不可估计。',
        '本批保持独立，不反馈修改。若后续据此调整候选或规则，须将整批转为开发数据，再单独冻结并生成新批次；不得把替代场景并入本批追认40/40。','',
        '## 产物与复核','',
        '- 冻结/排除清单：`deliverables/research174_independent_prepare_20261028_r01/`',
        '- 执行命令、原始日志、波形、逐场景判定：`deliverables/research174_independent_run_20261028_r01/`',
        '- 本报告、事务关联、触发映射和无曝光采样：本目录。','',
        '```powershell',
        'wsl -- python3 scripts/research174_independent_acceptance.py verify --prepared deliverables/research174_independent_prepare_20261028_r01',
        'wsl -- python3 scripts/research174_result_audit.py --prepared deliverables/research174_independent_prepare_20261028_r01 --run deliverables/research174_independent_run_20261028_r01 --out deliverables/research174_independent_report_recheck',
        '```','复核输出必须使用不存在的目录；不会重跑仿真或调用模型。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    g.s.seal_files(out)
    print('AUDITED174',len(checks),'checks; outcome remains37/40; model0; native0',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
