"""Summarize completed experiments without rerunning or changing any decision."""
import argparse
import json
from pathlib import Path
import shutil
import research17_loop as loop
from research34_campaign import digest

read,dump=loop.read,loop.dump


def report(out,local_report):
    out.mkdir(parents=True,exist_ok=False)
    base=loop.ROOT/'deliverables'
    remote36=read(base/'research36_report_20261022_r01/results.json')
    remote38=read(base/'research38_report_20261022_r01/results.json')
    timeout=read(base/'research37_report_20261022_r03/results.json')
    final=read(local_report/'results.json')
    assert all(r['passed'] for r in (remote36,remote38,timeout,final))
    classification=remote36['plans'][-1]['decision']
    assert classification['accepted'] and classification['windows']==13
    accepted=final['outcome']['accepted']
    independent=final['independent']
    test_pass=bool(independent and independent['all_five_pass_on_first_attributed_evidence'])
    stages=[dict(id=1,requirement='真实模型义务适用周期及事件判断',status='verified_development_only',
        evidence='research36 plan/v1:13/13 windows; independent event and original three-way gate passed'),
        dict(id=2,requirement='新模型SVA细化通过目标与历史门控',status='accepted_finite_evidence' if accepted else 'not_completed',
             evidence=final['outcome']),
        dict(id=3,requirement='同一冻结版本的新独立五义务验收',status='passed_first_attributed_scope' if test_pass else 'failed_or_unknown' if independent else 'not_executed',
             evidence=independent)]
    costs=[r['cost'] for r in (remote36,remote38,timeout,final)]
    calls=sum(c['model_calls'] for c in costs)
    missing=sum(c['usage_unavailable_calls'] for c in costs)
    totals=dict(remote_calls=remote36['cost']['model_calls']+remote38['cost']['model_calls'],
        local_calls=timeout['cost']['model_calls']+final['cost']['model_calls'],model_calls=calls,
        prompt_tokens_known_subtotal=sum(c['prompt_tokens_known_subtotal'] for c in costs),
        completion_tokens_known_subtotal=sum(c['completion_tokens_known_subtotal'] for c in costs),
        usage_unavailable_calls=missing,exact_total_tokens_available=missing==0,
        native_compile_calls=sum(c['native_compile_calls'] for c in costs),
        native_execute_calls=sum(c['native_execute_calls'] for c in costs),
        compile_smoke_execute_calls=sum(c['compile_smoke_execute_calls'] for c in costs),formal_calls=0,monetary_cost=None)
    management=[]
    for suffix in ('r01','r02','r03','r04'):
        path=base/f'research37_local_20261022_{suffix}/model/model_load/result.json'
        if path.exists(): management.append(dict(path=str(path),record=read(path)))
    totals['local_model_load_management_calls']=sum(r['record']['management_calls'] for r in management)
    totals['local_load_generation_calls_observed']=sum(r['record'].get('generation_calls') or 0 for r in management)
    totals['local_model_load_wall_seconds']=sum(r['record']['wall_seconds'] for r in management)
    preparations=[]
    for name in ('research37_local_20261022_r01','research37_local_20261022_r02'):
        folder=base/name
        preparations.append(dict(path=str(folder),outcome=read(folder/'outcome.json'),scope='Tokenizer context refusal, zero generation; cold model loading separately logged.'))
    fixes=read(base/'research38_feedback_check_20261022_r02/verification.json')
    case_analysis=read(base/'research36_case_analysis_20261022_r02/case_analysis.json')
    result=dict(stages=stages,all_three_completed_within_finite_scope=accepted and test_pass,
        final_frozen_hash=final['outcome']['frozen_hash'],final_history=final['history'],cost=totals,
        feedback_fix=fixes,context_prechecks=preparations,local_model_management=management,case_analysis=case_analysis,
        limits=['Artificial output faults on actual axis_fifo RTL, not an upstream historical bug.',
                'Single selected local continuation and finite sampled evidence; not cross-seed stability.',
                'Native simulation is not formal proof. Subsequent attribution unknowns are retained.',
                'Remote quota six calls consumed. Local exploratory model switch is not a controlled mechanism comparison.'])
    dump(out/'results.json',result)
    dump(out/'task_matrix.json',stages)
    files=[base/'research36_report_20261022_r01/results.json',base/'research38_report_20261022_r01/results.json',
           base/'research37_report_20261022_r03/results.json',local_report/'results.json',
           base/'research38_feedback_check_20261022_r02/verification.json',base/'research36_case_analysis_20261022_r02/case_analysis.json']
    dump(out/'source_manifest.json',{str(p):digest(p) for p in files})
    shutil.copy2(__file__,out/'report_source.py')
    lines=['# 本轮第1→第2→第3项实际完成情况','',
           '|任务|实际状态|','|---|---|']
    for row in stages:lines.append(f"|{row['id']}. {row['requirement']}|{row['status']}|")
    lines+=['','第1项保持原三分类门控，并增加事件判断。真实模型先错误读取复位状态，被拒绝后修正，最终13个开发窗口全部通过。不能推广为任意场景的规格理解。',
        'research36两次真实SVA分别检出6/8、8/8新目标，但分别新增15/17条义务级误报，均丢失2条历史检出、留下2条关键unknown。所有误报行均观测到数据前后保持、但与参考队列头不同。防退化拒绝没有被放宽。',
        '沿用research32既有“仅当前目标所在场景”规则的事后影子判定：v0拒绝，v1接受；实际历史门控均拒绝。v1是本轮真实新提案上的防退化拒绝案例，但该影子规则不等于复现包含公共历史场景的完整A/B消融，不能据此宣称受控机制收益或普遍优势。',
        'research38两次响应在项目接口校验阶段因 interface_unknown:rst 被拒绝，未进行原生编译。原第二次请求未携带具体错误，只给出了笼统失败，这是已定位的实现缺口；修复后的诊断传递及非法槽防护9项本地检查通过。尚不能把测试夹具或接口修复算作真实模型细化成功。',
        '本地Qwen的两次16K预检均没有生成调用；改用24K后首次真实调用在900秒超时，最终tokens不可用。最终有界尝试与原生结果详见本地报告。', '',
        f"最终冻结 `{result['final_frozen_hash']}`。", '', '最终本地修改记录：']
    for edit in final['edits']:
        lines+=['```json',json.dumps(edit.get('edit'),ensure_ascii=False,indent=2),'```',
                '接受：'+str(edit['decision']['accepted'])+'；原因：'+json.dumps([r['kind'] for r in edit['decision']['reasons']],ensure_ascii=False)]
    if independent:
        lines+=['',f"新的独立输入{independent['distinct_inputs']}条、场景{independent['scenarios']}个，五义务首个可归因证据验收{test_pass}。",'',
                '|义务|触发|检出|漏报|误报|当前unknown|','|---|---:|---:|---:|---:|---:|']
        for name,m in independent['metrics']['obligations'].items():lines.append(f"|{name}|{m['triggers']}|{m['detections']}|{m['misses']}|{m['false_positives']}|{m['unknown']}|")
        lines+=['','完整计数：'+json.dumps(independent['metrics']['counts'])]
    else:lines+=['','没有接受的新版本，因此没有执行新的独立验收；该项保持未完成。']
    lines+=['',f"实际远程调用{totals['remote_calls']}、本地调用{totals['local_calls']}；已知输入/输出tokens小计{totals['prompt_tokens_known_subtotal']}/{totals['completion_tokens_known_subtotal']}，另有{missing}次用量不可用，不能声称完整总tokens。原生编译{totals['native_compile_calls']}、执行{totals['native_execute_calls']}（含冒烟{totals['compile_smoke_execute_calls']}），形式化0，金额不可用。",'',
        f"另有本地冷加载管理请求{totals['local_model_load_management_calls']}次，观测到的生成调用{totals['local_load_generation_calls_observed']}次；加载耗时及原始响应另存，不把管理请求当作生成成功。",'',
        '有限历史保护保持不是全局保证；义务×采样行不是独立Bug数；人工故障不计为原始历史修复成功。未开展新的多种子机制收益验证。', '',
        '只读复核：','```powershell',
        'wsl -- python3 scripts/research36_audit.py --prepared deliverables/research36_prepare_20261022_r01 --run deliverables/research36_real_20261022_r01 --out deliverables/research36_audit_NEW',
        'wsl -- python3 scripts/research37_audit.py --run deliverables/research37_local_20261022_r04 --out deliverables/research37_audit_NEW',
        '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(dict(all_three=result['all_three_completed_within_finite_scope'],accepted=accepted,independent_pass=test_pass,cost=totals),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--local-report',required=True,type=Path)
    a=p.parse_args()
    report(a.out.resolve(),a.local_report.resolve())
