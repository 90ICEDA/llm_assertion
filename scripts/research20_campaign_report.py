"""Terminal-only Chinese campaign audit; no models or candidate changes.

Consumes six independently sealed run reports after every run has terminated.
Each physical run is charged once; continuation source costs are not re-added.
"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path
import shutil
import sys

import research17_report as base
import research18_report as prior
from research15_acceptance import inspect

ROOT=base.ROOT
RUNS=tuple(f'research20_closed_loop_20261018_r{i:02d}' for i in range(1,7))
QUALIFICATIONS=(
    ('research20_cases_20261018_r01','summary.json','既有故障模型的九组开发案例原生审计'),
    ('research20_mapping_qualification_20261018_r01','result.json','多个义务标签与原生证据映射资格检查'),
    ('research20_stall_qualification_20261018_r01','summary.json','人工背压故障的合法输入与漏报资格检查'),
    ('research20_feedback_projection_20261018_r01','qualification.json','真实反馈投影与上下文压缩检查'),
    ('research20_remote_qualification_20261018_r01','qualification.json','远程请求构造及历史真实响应解析；当时没有网络调用'),
    ('research20_initial_feedback_qualification_20261018_r01','qualification.json','初始接口拒绝反馈保留及直接性质语法检查'),
)


def sum_cost(costs):
    keys=('model_calls','prompt_tokens_known_subtotal','completion_tokens_known_subtotal',
        'usage_unavailable_calls','model_wall_seconds_known_subtotal','model_wall_seconds_unavailable_calls',
        'native_compile_calls','native_execute_calls','compile_smoke_execute_calls',
        'native_compile_wall_seconds','native_execute_wall_seconds','native_commands_failed_or_timed_out',
        'tool_version_query_calls','formal_calls')
    total={k:sum(c.get(k,0) or 0 for c in costs) for k in keys}
    total['prompt_tokens_total']=total['prompt_tokens_known_subtotal'] if not total['usage_unavailable_calls'] else None
    total['completion_tokens_total']=total['completion_tokens_known_subtotal'] if not total['usage_unavailable_calls'] else None
    total['monetary_cost']=None
    return total


def scope_text(counts):
    if not counts:return '未执行或不可用'
    return ' / '.join(str(counts.get(k,'不可用')) for k in ('detections','misses','false_positives','unknown','triggers'))


def independent_stall_examples(run):
    """Post-freeze diagnosis only; never modifies a frozen set or prompts."""
    path=run/'core_independent/core/independent_ledger.json'
    if not path.exists():return []
    parsed=inspect(base.read(path)['ledger']);result=[]
    for key in sorted(parsed['misses']):
        row=parsed['rows'][key]
        if row['obligation']!='stall_stability':continue
        source=prior.portable_path(row['source_directory'])
        samples=base.read(source/'reference_trace.json',[])
        cycle=row['cycle'];bycycle={s['cycle']:s for s in samples}
        previous,current=bycycle.get(cycle-1),bycycle.get(cycle)
        reasons=[]
        if previous and current:
            if previous['mvalid'] and not previous['mready'] and current['mready']:
                reasons.append('上一拍输出受背压，本拍解除背压；已接受模型性质额外要求本拍仍 !mready，因此本拍不检查稳定性。')
            if previous['mvalid'] and not previous['mready'] and not current['mvalid']:
                reasons.append('上一拍输出受背压，本拍valid撤回；性质要求本拍mvalid，未覆盖valid保持义务。')
        if not reasons:reasons.append('原生证据表明目标未检出；保留实际采样值，不推断未验证原因。')
        fixed=source.parent/'correct'
        result.append(dict(evidence_id=key,scenario=row['scenario_id'],variant=row['variant'],cycle=cycle,
            oracle=row['oracle'],violation=row['oracle_violation'],native=row['native'],
            samples=[s for s in samples if cycle-1<=s['cycle']<=cycle+1],
            fixed_samples=[s for s in base.read(fixed/'reference_trace.json',[]) if cycle-1<=s['cycle']<=cycle+1],
            reason=reasons,source=str(source),post_test_diagnosis_only=True))
        if len(result)==2:break
    return result


def build(out):
    out=out.resolve()
    if ROOT not in out.parents:raise ValueError('workspace output required')
    # Check all terminal outcomes before opening any report containing tests.
    for name in RUNS:
        run=ROOT/'deliverables'/name
        outcome=base.read(run/'outcome.json',{})
        if outcome.get('status') in (None,'running'):
            raise RuntimeError('campaign still active; independent results not read: '+name)
        if not (run/'report/results.json').exists() or not (run/'report/verification.json').exists():
            raise RuntimeError('sealed report not available: '+name)
    records=[];refs={}
    def reference(path):
        path=Path(path).resolve()
        if ROOT not in path.parents:raise ValueError('unsafe reference')
        refs[path.relative_to(ROOT).as_posix()]=base.digest(path)
    for name in RUNS:
        run=ROOT/'deliverables'/name
        report=base.read(run/'report/results.json')
        verification=base.read(run/'report/verification.json')
        if not verification.get('passed'):raise RuntimeError('run integrity audit failed: '+name)
        for p in (run/'report/results.json',run/'report/REPORT.md',run/'report/verification.json',run/'report/manifest.json',run/'outcome.json'):
            reference(p)
        for p in (run/'report').rglob('*'):
            if p.is_file():reference(p)
        # Carry the sealed underlying native/model hashes into the campaign
        # manifest, so --verify checks actual evidence, not only old reports.
        for rel,expected in base.read(run/'report/manifest.json').items():
            path=(run/rel).resolve()
            if run not in path.parents:raise ValueError('unsafe nested run manifest')
            refs[path.relative_to(ROOT).as_posix()]=expected
        records.append(dict(name=name,status=report['status'],
            initial_source=report['initial_source'],initial_candidate=report['initial_candidate'],
            final_candidate=report['core_candidate'],model_trace=report['model_trace'],core=report['core'],
            missing_evidence=report['missing_evidence'],
            independent=report['independent'],independent_deduplicated=report['independent_deduplicated'],
            independent_stall_misses=independent_stall_examples(run),
            cost=report['cost']['total'],model_calls=report['cost']['model_calls'],
            context_preflight=report['context_preflight_audit'],management=report['management_operations'],
            command=report['execution_command'],diagnosis=report['diagnosis'],
            verification=dict(passed=True,checked=verification.get('checked')),
            reused_source=report['reused_core_source_audit'],
            source_cost_readded=False,report=str(run/'report/REPORT.md')))
    qualifications=[]
    for name,file,label in QUALIFICATIONS:
        folder=ROOT/'deliverables'/name
        value=base.read(folder/file)
        if value is None:raise RuntimeError('qualification missing: '+name)
        files=base.artifacts(folder)
        physical=base.cost_audit(folder,files)
        for path in files:reference(path)
        checks=value.get('checks',[])
        qualifications.append(dict(name=name,description=label,
            passed=value.get('passed',value.get('healthy')),check_count=len(checks),
            result_file=str(folder/file),cost=physical['total'],
            scope=value.get('scope',value.get('limitation',value.get('simulation_scope')))))
    run_cost=sum_cost([r['cost'] for r in records])
    qualification_cost=sum_cost([q['cost'] for q in qualifications])
    total=sum_cost([run_cost,qualification_cost])
    source=next(r for r in records if r['name']==RUNS[4])
    trajectory=[t for t in source['model_trace']['records'] if t['accepted']]
    if any(not t.get('accepted_integrity_passed') for t in trajectory):raise RuntimeError('accepted model trace integrity failed')
    local_calls=sum(len(r['model_calls']) for r in records[:3])
    remote_calls=sum(len(r['model_calls']) for r in records[3:])
    result=dict(generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        scope='Research20 six actual runs and six qualifications. Finite simulation of real axis_fifo plus artificial output-boundary faults.',
        all_model_work_terminal=True,records=records,qualifications=qualifications,
        accepted_real_model_edits=trajectory,
        cost=dict(runs=run_cost,qualifications=qualification_cost,total=total,local_model_calls=local_calls,
            remote_model_calls=remote_calls,remote_authorized_cap=8,
            approval_rejected_command=dict(started=False,model_calls=0),
            accounting='Count each physical attempt and native command once. Failed runs included. No imported source cost added again; preflight-only rejection and copied frozen candidates are not model calls. Provider raw usage not summed twice. Monetary cost unavailable.'),
        acceptance_matrix=[
            dict(requirement='真实模型生成并原生执行',status='已验证',evidence='r05新初始生成与原生资格检查通过；完整远程响应字节与模型表达式留存。'),
            dict(requirement='独立契约判定有效漏报',status='已验证于人工故障模型',evidence='固定开发输入的两参数配对原生执行，独立接受事务队列确认drop、reset_residue、stall_glitch缺口。'),
            dict(requirement='自动细化与历史防退化',status='局部已验证',evidence='r05排空与背压两条新模型编辑开发验收接受，全部历史回放；复位两次及r06一次拒绝。'),
            dict(requirement='复杂FIFO时序',status='已执行',evidence='开发depth2/pipeline0与depth5/pipeline1，独立depth4/pipeline2；连续握手、重叠、背压、复位与多周期响应。'),
            dict(requirement='冻结后独立验证',status='已执行且保留失败',evidence='r05、r06两批新输入。背压独立仍漏报；复位/非请求输出未补齐；r05保留unknown。'),
            dict(requirement='完整五项功能义务保护',status='未完成',evidence='不能把三个有检出标签当作完整规范证明，剩余漏报与unknown明确保留。'),
            dict(requirement='四组消融与多种子对比',status='本轮未新增',evidence='初始/最终冻结回放是候选比较，不是四组消融；不同模型的失败尝试不构成公平机制对比。'),
            dict(requirement='真实历史父Bug闭环',status='未完成',evidence='人工输出边界故障不能计原始历史FIFO或stat成功。')],
        whole_parent_passed=False,formal_proof=False,global_nonregression=False,
        new_ablation=False,new_multiseed_mechanism_comparison=False,
        historical_parent_successes=0)
    out.mkdir(parents=True,exist_ok=False)
    base.dump(out/'results.json',result)
    (out/'REPORT.md').write_text(render(result),encoding='utf-8')
    shutil.copy2(__file__,out/'report_script_snapshot.py')
    base.dump(out/'execution.command.json',dict(argv=[sys.executable,*sys.argv],cwd=str(Path.cwd()),
        purpose='Terminal campaign aggregation only; no model or native execution.'))
    for path in out.iterdir():
        if path.is_file():reference(path)
    base.dump(out/'manifest.json',refs)
    verify(out)
    print({'total':total,'local_calls':local_calls,'remote_calls':remote_calls,'report':str(out/'REPORT.md')})


def render(result):
    total=result['cost']['total'];runs=result['records'];r05=runs[4];r06=runs[5]
    lines=['# RTL/SVA 本轮真实实验汇总（2026-10-18）','',
        '**本轮取得新模型自动细化的实际局部成功，但完整五项义务保护仍未完成。** r05新生成初始断言，随后新模型提出的排空与背压互补断言通过开发原生执行和历史保护验收；冻结后独立测试表明背压性质仍漏报。复位/非请求输出修改未通过，拒绝版本保留。',
        '', '真实主设计为 axis_fifo，故障是显式人工输出边界变异。新增背压变异不改变接口规范，但不是历史缺陷发现。仿真有限证据不构成形式证明，历史保护保持不构成全局防退化。',
        '', '## 验收矩阵','', '| 要求 | 状态 | 证据与限制 |','|---|---|---|']
    for row in result['acceptance_matrix']:
        lines.append(f"| {row['requirement']} | {row['status']} | {row['evidence']} |")
    lines+=['','## 六次实际运行（失败全部保留）','',
        '| 运行 | 终态 | 模型 | 真模型调用 | 输入/输出 tokens | 原生编译/执行 | 新接受编辑 |',
        '|---|---|---|---:|---:|---:|---:|']
    for run in runs:
        c=run['cost'];edits=run['model_trace']['accepted_new_target_edits']
        models=','.join(sorted({str(call.get('model')) for call in run['model_calls']}))
        lines.append(f"| {run['name']} | {run['status']} | {models} | {c['model_calls']} | {c['prompt_tokens_known_subtotal']}/{c['completion_tokens_known_subtotal']} | {c['native_compile_calls']}/{c['native_execute_calls']} | {edits} |")
    lines+=['', 'r01初始成功但六次细化在分词预检阶段被拒绝，没有提交模型；r02真实局部模型调用的编辑全部拒绝；r03两次初始性质原生资格失败；r04远程两次响应被性质接口拒绝；r05远程五次调用取得初始与两条新编辑接受；r06复用r05冻结集合，仅新增一次复位修改调用，仍被拒绝，未新增接受。',
        '', 'r05与r06的初始含义不同：r05从新生成单义务候选开始，r06从r05已接受集合开始。复用不算新生成，r06独立候选比较相同集合也不能算新改善。','',
        'r05初始生成任务明确只要求 `order_payload`，属于受控局部候选；其他义务在后续步骤补充。因此初始/最终改善不能证明优于“一次性依据全部规格生成完整断言集合”，也不是公平机制优越性比较。','',
        '## 两条真实模型修改轨迹','', 'r05真实初始断言：','```systemverilog']
    lines += [a['property'] for a in (r05['initial_candidate'] or {}).get('assertions',[])]+['```']
    for trace in result['accepted_real_model_edits']:
        h=trace['history'];edit=trace['edit'];before=h['before'];after=h['after'];obs=h['requested_obligations']
        lines+=['',f"### {','.join(obs)}：{trace['version']}",'',
            '模型实际理由：'+edit.get('reason','不可用'),'', '模型新增/修改的性质原文：','```systemverilog']
        lines += [a.get('property',str(a)) for a in edit.get('assertions',[])]+['```','',
            f"开发回放：检出 {before['detections']}→{after['detections']}，漏报 {before['misses']}→{after['misses']}，误报 {after['false_positives']}，unknown {after['unknown']}。原生历史验收接受；表达式原样组装核验 {trace['accepted_integrity_passed']}。"]
        if 'drain_no_loss' in obs:
            lines+=['','证据是已接受尾部事务在周期111的有限公平排空检查仍未完成，正确对照已响应。接受只说明当前证据被检出；模型表达式并不等同于普遍的 `ref_count==0` 规格，不能从几个样本推断逻辑等价。']
        if 'stall_stability' in obs:
            lines+=['','人工背压故障在开发周期6/7改变未被接受输出的数据；请求实际周期3已接受，正确响应周期10。新增性质检查连续两拍仍受背压时的数据保持，但没有完整覆盖valid保持，也没有覆盖解除背压当拍。独立测试确实保留了漏报，不能称这条完整链成功。']
    lines+=['','### r06最后一次真实修改仍被拒绝','',
        'r06从r05已接受集合出发，仅尝试尚未解决的复位/非请求输出义务；不是重新生成初始候选。']
    for trace in r06['model_trace']['records']:
        edit=trace.get('edit') or {};history=trace['history']
        lines+=['', '实际模型提案：','```systemverilog']
        lines += [a.get('property',str(a)) for a in edit.get('assertions',[])]+['```',
            '拒绝原因：'+__import__('json').dumps(history['decision'].get('reasons',[]),ensure_ascii=False),
            '该提案因 `interface_unknown:rst` 未进入原生执行；本次模型调用及原已接受冻结集合的开发/独立回放计入成本。冻结集合保留上一次已接受版本。']
    lines+=['','## 冻结后的独立结果','',
        '两批独立结果在所有模型工作结束后才被读取。没有据此再改候选。表中“检出/漏报/误报/unknown/触发”为去重后的义务记录，不是独立Bug数量。', '',
        '| 运行 | 冻结候选 | 义务 | 目标违例分母 | 正确控制行 | 检出/漏报/误报/unknown/触发 |','|---|---|---|---:|---:|---|']
    for run in (r05,r06):
        for name,data in run['independent_deduplicated'].items():
            for ob,counts in data['by_obligation'].items():
                lines.append(f"| {run['name']} | {name} | {ob} | {counts['target_oracle_rows']} | {counts['correct_control_rows']} | {scope_text(counts)} |")
            lines.append(f"| {run['name']} | {name} | 后续归因 unknown（另存） | — | — | {data['later_attribution_unknown_raw']} |")
            lines.append(f"| {run['name']} | {name} | 原始/去重义务记录 | {data['raw_rows']}/{data['unique_rows']} | — | 漏报采样事件 {data['missed_events']} |")
    for run in (r05,r06):
        for miss in run['independent_stall_misses'][:1]:
            lines+=['',f"背压负例：`{run['name']}`，`{miss['scenario']}`，周期 {miss['cycle']}。",' '.join(miss['reason']),
                '', '实际采样：','```json',__import__('json').dumps(miss['samples'],ensure_ascii=False,indent=2),'```',
                '这是一份测试后诊断记录，没有用于本轮生成或重新挑选冻结候选。']
    lines+=['','## 资格检查和实际总成本','', '| 检查 | 通过 | 原生编译/执行 |','|---|---|---|']
    for q in result['qualifications']:
        lines.append(f"| {q['description']} | {q['passed']} | {q['cost']['native_compile_calls']}/{q['cost']['native_execute_calls']} |")
    lines+=['',f"六次运行及资格实验合计：真实模型调用 **{total['model_calls']}**（本地 {result['cost']['local_model_calls']}、远程 {result['cost']['remote_model_calls']}）；输入 tokens 已知小计 **{total['prompt_tokens_known_subtotal']}**，输出 **{total['completion_tokens_known_subtotal']}**，用量不可用调用 {total['usage_unavailable_calls']}。原生编译 **{total['native_compile_calls']}**、执行 **{total['native_execute_calls']}**（包含编译smoke {total['compile_smoke_execute_calls']}），形式化调用 **{total['formal_calls']}**。金额不可用。",'',
        '远程授权8次已使用完。最初被审批拦截的命令未启动，计0请求。失败调用计入，预检拒绝不计模型生成，r06来源历史成本不重复加总；provider usage和归一化tokens不双计。',
        '', '## 可复现命令与产物','', '以下为实际执行记录；重新执行必须更换输出目录。资格审计及每次运行的源码、参数、请求响应、日志和波形由对应报告清单索引。','', '```powershell']
    for run in (r05,r06):lines.append((run['command'] or {}).get('command','启动记录不可用'))
    lines += ['wsl -- python3 scripts/research20_campaign_report.py --out deliverables/research20_campaign_20261018_r02',
        'wsl -- python3 scripts/research20_campaign_report.py --out deliverables/research20_campaign_20261018_r01 --verify','```','',
        '各运行报告：']
    lines += [f"- [{r['name']}](../{r['name']}/report/REPORT.md)" for r in runs]
    lines += ['', '## 明确未完成','',
        '- 复位取消与非请求输出保护尚未通过严格验收；冻结集合继续保留旧版本。',
        '- 背压数据保持只在部分条件上改善，独立仍漏报；valid保持和解除背压当拍未完整保护。',
        '- r05独立unknown与所有后续归因unknown保留，不排除困难样本来声称全通过。',
        '- 完整五项义务、整个父案例、真实历史缺陷闭环仍未完成；stat与原始FIFO历史问题仍unknown。',
        '- 本轮没有新四组消融、真正候选对分歧比较、多种子公平机制比较或形式化证明。',
        '- 远程调用预算已用完；下一轮改进需要新实验预算并重新准备未见独立数据。已读取的本轮测试若用于修改，须转开发数据。','']
    return '\n'.join(lines)


def verify(out):
    out=Path(out).resolve();manifest=base.read(out/'manifest.json')
    if not manifest:raise RuntimeError('manifest missing')
    failures=[];parents={}
    for index,(rel,expected) in enumerate(manifest.items(),1):
        raw=ROOT/rel
        # Reuse resolved parent directories within this read-only scan. All
        # file bytes are still rehashed, and final symlinks are resolved too.
        # Avoid thousands of redundant ancestor-stat round trips on /mnt/d.
        if raw.parent not in parents:parents[raw.parent]=raw.parent.resolve()
        path=parents[raw.parent]/raw.name
        if path.is_symlink():path=path.resolve()
        if ROOT not in path.parents:raise ValueError('unsafe manifest path')
        actual=base.digest(path) if path.is_file() else None
        if actual!=expected:failures.append(dict(path=rel,expected=expected,actual=actual))
        if index%2000==0:print({'verified_files':index,'of':len(manifest)},flush=True)
    result=dict(passed=not failures,checked=len(manifest),failures=failures,
        scope='Campaign files, all qualification artifacts, six sealed reports, and every native/model artifact transcribed from the sealed run manifests; actual bytes rehashed.')
    base.dump(out/'verification.json',result)
    if failures:raise SystemExit(1)
    print({'verified':True,'checked':len(manifest)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify:verify(args.out)
    else:build(args.out)


if __name__=='__main__':main()
