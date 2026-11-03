"""Read archived research17 results; write only RUN/report, never model feedback.

No model request or RTL execution. Invoke after the run has stopped. Without
outcome.json, report incomplete without reading independent-test contents.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
CORE_OBLIGATIONS=('order_payload','drain_no_loss')
ALL_OBLIGATIONS=(*CORE_OBLIGATIONS,'no_unsolicited_output','stall_stability','reset_cancellation')


def read(path,default=None):
    return json.loads(Path(path).read_text(encoding='utf-8-sig')) if Path(path).exists() else default


def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def candidate_sha(candidate):
    return hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def phase(rel):
    parts=Path(rel).parts
    return '/'.join(parts[:2]) if parts and parts[0]=='arms' else parts[0] if parts else 'unknown'


def artifacts(run):
    return sorted(p for p in run.rglob('*') if p.is_file() and not p.is_symlink()
                  and p.relative_to(run).parts[0]!='report')


def cost_audit(run,files):
    calls=[];commands=[];native=[]
    for p in files:
        rel=p.relative_to(run).as_posix()
        if p.name=='attempt.json' and p.parent.name=='model_call':
            result=read(p.parent/'result.json',read(p.parent/'transport_result.json',{}))
            request=read(p.parent/'request.json',{})
            calls.append(dict(path=rel,phase=phase(rel),status=result.get('status','unknown'),
                candidate_status=result.get('candidate_status','unknown'),operation=result.get('operation'),
                prompt_tokens=result.get('prompt_tokens'),completion_tokens=result.get('completion_tokens'),
                wall_seconds=result.get('wall_seconds'),model=request.get('model'),options=request.get('options'),
                format_sha256=candidate_sha(request.get('format')),retries=result.get('retries')))
        if p.name in ('compile.json','execute.json','tool_version.json'):
            value=read(p,{})
            if isinstance(value,dict) and 'argv' in value:
                commands.append(dict(path=rel,phase=phase(rel),kind=p.stem,
                    smoke=p.name=='execute.json' and (p.parent/'compile.json').exists(),**value))
        if p.name=='result.json' and ((p.parent/'compile.json').exists() or (p.parent/'execute.json').exists()):
            value=read(p,{})
            if isinstance(value,dict) and 'engine' in value:
                native.append(dict(path=rel,**{k:value.get(k) for k in (
                    'compile_status','compile_error_category','tool_support_status','execution_status',
                    'trigger_status','property_status','tool_version')}))
    def summarize(cs,cmds):
        known=lambda key:sum(c.get(key) or 0 for c in cs)
        missing=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in cs)
        return dict(model_calls=len(cs),prompt_tokens_known_subtotal=known('prompt_tokens'),
            completion_tokens_known_subtotal=known('completion_tokens'),usage_unavailable_calls=missing,
            prompt_tokens_total=known('prompt_tokens') if not any(c.get('prompt_tokens') is None for c in cs) else None,
            completion_tokens_total=known('completion_tokens') if not any(c.get('completion_tokens') is None for c in cs) else None,
            model_wall_seconds_known_subtotal=known('wall_seconds'),
            model_wall_seconds_unavailable_calls=sum(c.get('wall_seconds') is None for c in cs),
            model_status=dict(Counter(c['status'] for c in cs)),
            native_compile_calls=sum(c['kind']=='compile' for c in cmds),
            native_execute_calls=sum(c['kind']=='execute' for c in cmds),
            compile_smoke_execute_calls=sum(c['smoke'] for c in cmds),
            native_compile_wall_seconds=sum(c.get('wall_seconds') or 0 for c in cmds if c['kind']=='compile'),
            native_execute_wall_seconds=sum(c.get('wall_seconds') or 0 for c in cmds if c['kind']=='execute'),
            native_commands_failed_or_timed_out=sum(c.get('exit_code')!=0 for c in cmds if c['kind']!='tool_version'),
            tool_version_query_calls=sum(c['kind']=='tool_version' for c in cmds),formal_calls=0)
    total=summarize(calls,commands)
    phases={p:summarize([c for c in calls if c['phase']==p],[c for c in commands if c['phase']==p])
            for p in sorted({c['phase'] for c in calls+commands})}
    recorded=read(run/'model_cost.json')
    crosscheck=None if recorded is None else dict(
        calls_match=recorded.get('calls')==total['model_calls'],
        known_prompt_tokens_match=recorded.get('prompt_tokens')==total['prompt_tokens_known_subtotal'],
        known_completion_tokens_match=recorded.get('completion_tokens')==total['completion_tokens_known_subtotal'],
        unavailable_calls_match=recorded.get('usage_unavailable')==total['usage_unavailable_calls'])
    return dict(total=total,by_phase=phases,model_calls=calls,native_commands=commands,
        native_status_counts={k:dict(Counter(v[k] if v[k] is not None else 'unavailable' for v in native))
            for k in ('compile_status','compile_error_category','tool_support_status','execution_status','trigger_status','property_status')},
        native_records=native,recorded_model_cost=recorded,recorded_model_cost_crosscheck=crosscheck,
        accounting='Physical attempt/compile/execute records, charged once; compile smoke included. No duplicated copied compile metadata. Search shared by B/D; pilot separate; wall sums are not elapsed makespan. Dollar cost unavailable.',
        monetary_cost=None)


def freeze_audit(run):
    records=[]
    for folder in [run/'core',*(run/'arms'/a for a in ('A','B','C','D'))]:
        freeze=read(folder/'freeze.json');candidate=read(folder/'frozen_candidate.json')
        if freeze is None and candidate is None:continue
        actual=candidate_sha(candidate) if candidate is not None else None
        records.append(dict(scope=folder.relative_to(run).as_posix(),expected=(freeze or {}).get('candidate_sha256'),
            actual=actual,passed=bool(freeze and candidate and freeze.get('candidate_sha256')==actual),freeze=freeze))
    initial=read(run/'shared_initial.json');stamp=read(run/'shared_initial_freeze.json')
    if initial is not None or stamp is not None:
        records.append(dict(scope='shared_initial',expected=(stamp or {}).get('hash'),
            actual=candidate_sha(initial) if initial is not None else None,
            passed=bool(initial and stamp and candidate_sha(initial)==stamp.get('hash'))))
    all_arms=read(run/'all_arms_freeze.json')
    if all_arms is not None:
        for arm,expected in all_arms.items():
            c=read(run/'arms'/arm/'frozen_candidate.json')
            records.append(dict(scope='all_arms/'+arm,expected=expected,actual=candidate_sha(c) if c else None,
                passed=bool(c and candidate_sha(c)==expected)))
    return records


def accepted_mapping(run,relative,summary):
    """Project only the accepted development replay, never a rejected proposal."""
    from research15_acceptance import inspect
    chosen=run/relative/'before/result.json'
    for h in summary.get('history',[]):
        if h.get('decision',{}).get('accepted'):
            chosen=run/relative/f"v{h['iteration']}"/'native/result.json'
    record=read(chosen,{})
    group=record.get('group') or {}
    if not group.get('ledger'):return dict(status='unavailable')
    parsed=inspect(group['ledger'])
    return dict(status='available',source=chosen.relative_to(run).as_posix(),mapping=parsed['mapping'],
        unknown_evidence=sorted(parsed['unknown']),malformed_evidence=parsed['errors'],
        unresolved_gap_evidence=sorted(parsed['misses']|parsed['false_positives']),
        later_attribution_unknown=group.get('exclusions',[]),
        unprotected_or_untriggered_obligations=[o for o in ALL_OBLIGATIONS
            if not parsed['mapping'].get(o,{}).get('trigger_evidence')],
        scope='Accepted development replay only; declared obligation mapping, not semantic entailment proof.')


def test_audit(run,name,freezes):
    summary=read(run/name/'summary.json')
    split=read(run/name/'split.json')
    if summary is None:return dict(status='not_completed',summary=None,split=split)
    checks=[]
    for arm,expected in (split or {}).get('hashes',{}).items():
        scope='core' if arm=='core' else 'arms/'+arm
        actual=next((f['actual'] for f in freezes if f['scope']==scope),None)
        checks.append(dict(candidate=arm,expected=expected,actual=actual,passed=actual is not None and expected==actual))
    return dict(status='completed',summary=summary,split=split,freeze_matches=checks,
        all_frozen_hashes_match=bool(checks) and all(c['passed'] for c in checks),
        independence='Inputs recorded as created after freeze; no report output fed to models. This report does not establish an external preregistration timestamp.')


def independent_scope(test,candidate,obligations):
    item=(test.get('summary') or {}).get(candidate)
    if not item:return dict(status='not_tested',passed=False,obligations=list(obligations))
    by=item.get('by_obligation',{})
    detail={o:by.get(o) for o in obligations}
    passed=bool(test.get('all_frozen_hashes_match') and item.get('healthy'))
    for counts in detail.values():
        passed &= bool(counts and counts.get('detections',0)>0 and counts.get('triggers',0)>0
                       and all(counts.get(k)==0 for k in ('misses','unknown','false_positives')))
    later=(item.get('counts') or {}).get('later_attribution_unknown')
    return dict(status='passed_on_recorded_scope' if passed else 'not_established',passed=passed,
        obligations=detail,later_attribution_unknown_in_entire_batch=later,
        note='Later violations remain separately unknown; a pass here applies only to these projected first-attribution obligations, not entire transactions or whole-case completeness.')


def render(run,result):
    cost=result['cost']['total'];core=result['core'];chain=result['core_chain'];comp=result.get('search_comparison') or {}
    lines=['# 真实模型与原生 SVA 闭环运行报告','',
        f"运行状态：`{result['status']}`。核心两义务链验收：`{chain['status']}`。全五义务案例通过：**未建立**。",'',
        '主案例为真实 axis_fifo RTL 加人工输出边界故障，不能计为原始 FIFO presented 历史缺陷复现成功。stat 规格/来源仍 unknown；其他父 Bug 本轮未新增成功。有限仿真和历史回放不构成形式证明或全局防退化保证。','',
        '## 实际修改轨迹','',
        '初始与最终 SVA 均直接来自真实模型表达式及模型时序选择；通用组装器没有人工修正表达式。','',
        '| 阶段 | 迭代 | 模型/接口状态 | 接受 | 原因 |','|---|---:|---|---|---|']
    for name,data in [('core',core),*sorted(result['arms'].items())]:
        for h in (data.get('history') or []):
            call=h.get('call',{});decision=h.get('decision',{})
            reasons=','.join(r.get('kind','unknown') for r in decision.get('reasons',[])) or '见实际验收记录'
            lines.append(f"| {name} | {h.get('iteration')} | {call.get('status')}/{call.get('candidate_status')} | {decision.get('accepted')} | {reasons} |")
    lines+=['','初始断言：','```systemverilog']
    initial=result.get('initial_candidate') or {}
    lines += [a['property'] for a in initial.get('assertions',[])]+['```','','核心冻结断言：','```systemverilog']
    lines += [a['property'] for a in (result.get('core_candidate') or {}).get('assertions',[])]+['```','',
        f"严格搜索见证：{len(result.get('strict_witnesses') or [])} 个检查记录，其中 {sum(bool(x.get('valid')) for x in result.get('strict_witnesses') or [])} 个有效；两个参数配置中的同一义务/故障不能重复计为独立缺口。",'']
    for i,w in enumerate((result.get('strict_witnesses') or [])[:2]):
        lines.append(f"案例 {i+1}：义务 `{w.get('obligation')}`，故障 `{w.get('fault_mode')}`，周期 {w.get('cycle')}，漏报类型 `{w.get('miss_subtype')}`；五条件 `{w.get('conditions')}`。")
        for aligned in w.get('aligned_transactions',[])[:2]:
            b=aligned.get('buggy') or {};f=aligned.get('fixed') or {}
            lines.append(f"事务 `{b.get('transaction_id')}` 在周期 {b.get('accept_cycle')} 接受；fixed 响应周期 {f.get('response_cycle')}，buggy 响应周期 {b.get('response_cycle')}、结果 `{b.get('outcome')}`。")
        lines.append('')
    lines+=['## 小规模搜索对比','','| 方法 | 查询 | 原生回放 | 独立缺口类 | 跨种子重复 | unknown查询 |','|---|---:|---:|---:|---:|---:|']
    for name,v in comp.get('methods',{}).items():
        lines.append(f"| {name} | {v.get('queries')} | {v.get('native_replays')} | {v.get('unique_gap_count')} | {v.get('recomputed_cross_seed_duplicate_gap_observations')} | {v.get('unknown_queries')} |")
    lines+=['',f"候选分歧适用状态：`{comp.get('candidate_disagreement_eligible','unavailable')}`。单条 property 的分歧方法不能作为真实候选分歧收益证据。各方法具体缺口键、契约新增键和信息预算保留在 results.json；不预设契约法优于其他方法。",'',
        '## 独立回放与范围','','| 测试批次/组 | 检出 | 漏报 | 合法误报 | unknown | 后续归因unknown |','|---|---:|---:|---:|---:|---:|']
    for name,test in result['independent'].items():
        for arm,entry in (test.get('summary') or {}).items():
            c=entry.get('counts') or {}
            lines.append(f"| {name}/{arm} | {c.get('detections')} | {c.get('misses')} | {c.get('false_positives')} | {c.get('unknown')} | {c.get('later_attribution_unknown')} |")
    lines+=['','计数单位为“义务×采样周期证据行”，不是独立 Bug 数。所有后续归因 unknown 单列保留，未从全案例结论中删除。每义务明细和缺失测试状态见 results.json。独立测试不得用于选择或修改本次冻结版本。','',
        '## 成本与可复核命令','',
        f"真实模型调用 {cost['model_calls']} 次；已知输入 tokens {cost['prompt_tokens_known_subtotal']}，输出 tokens {cost['completion_tokens_known_subtotal']}；usage 缺失 {cost['usage_unavailable_calls']} 次。",'',
        f"原生编译 {cost['native_compile_calls']} 次；执行 {cost['native_execute_calls']} 次（含编译附带 smoke {cost['compile_smoke_execute_calls']} 次）；形式化调用 {cost['formal_calls']}。模型、编译及执行的每阶段实际耗时见 cost/results.json；失败调用照常计费，缺失值不按零声称完整总量。",'',
        '各组最大预算相同，不保证实际成本相等。初始生成和搜索为共享成本，核心 pilot 单独计费；B/D 使用同一实际搜索见证，不把一次搜索冒充两次独立发现。','',
        '在仓库根目录可执行同一实验入口（运行目录必须未使用）：','```powershell',
        'wsl -- python3 scripts/research17_loop.py --out deliverables/research17_closed_loop_20261016_r02','```','',
        '对本次已完成产物生成只读汇总：','```powershell',
        f'wsl -- python3 scripts/research17_report.py --run {run.relative_to(ROOT).as_posix()}',
        f'wsl -- python3 scripts/research17_report.py --run {run.relative_to(ROOT).as_posix()} --verify','```','',
        '## 尚未建立的结论','',
        '- 不把两项义务改善等同于所有五项义务完整保护；无完整独立触发/违例证据的义务保持未验证。',
        '- 没有真实历史 FIFO presented 缺陷新见证，也没有 stat 时序/来源新证明。',
        '- 深度参数、有限背压/复位场景和单模型单种子结果不能推为全参数或统计显著优势。',
        '- 若核心失败或任一测试未完成，results.json 保留具体状态和原始拒绝轨迹，不替代成成功。','',
        '封存清单排除 report 自身以避免递归；source_and_rtl_hashes.json 包含运行源码快照、RTL 与原生 testbench 哈希，freeze_checks.json 核对最终集合与测试使用哈希。']
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,default=ROOT/'deliverables/research17_closed_loop_20261016_r01')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();run=args.run.resolve()
    if ROOT not in run.parents:raise ValueError('Run must be inside workspace')
    if not run.is_dir():raise ValueError('Run directory does not exist')
    out=run/'report';out.mkdir(exist_ok=True)
    if args.verify:
        manifest=read(out/'manifest.json')
        if not manifest:raise ValueError('Missing nonempty manifest')
        checks=[]
        for rel,expected in manifest.items():
            p=(run/rel).resolve()
            if run not in p.parents:raise ValueError('Unsafe manifest path')
            actual=digest(p) if p.is_file() else None
            checks.append(dict(path=rel,passed=actual==expected,expected=expected,actual=actual))
        extra=sorted({p.relative_to(run).as_posix() for p in artifacts(run)}-set(manifest))
        verified=dict(passed=all(x['passed'] for x in checks) and not extra,checked=len(checks),checks=checks,
            unmanifested_files=extra)
        dump(out/'verification.json',verified)
        print(json.dumps({k:v for k,v in verified.items() if k!='checks'}))
        if not verified['passed']:raise SystemExit(1)
        return
    outcome=read(run/'outcome.json');files=artifacts(run)
    cost=cost_audit(run,files);freezes=freeze_audit(run)
    # Deliberately never inspect holdout contents while no terminal outcome exists.
    tests={name:test_audit(run,name,freezes) if outcome is not None else dict(status='not_read_run_incomplete')
           for name in ('core_independent','ablation_independent')}
    core=read(run/'core/summary.json',{});witnesses=read(run/'search/strict_witnesses.json',[])
    projected=independent_scope(tests['core_independent'],'core',CORE_OBLIGATIONS)
    chain=bool(outcome and core.get('resolved') and core.get('has_acquired_gap') and witnesses
        and any(w.get('valid') for w in witnesses) and projected['passed']
        and any(f['scope']=='core' and f['passed'] for f in freezes)
        and any(h.get('decision',{}).get('accepted') and h.get('decision',{}).get('gate_enforced') for h in core.get('history',[])))
    result=dict(status=(outcome or {}).get('status','incomplete'),generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        protocol=read(run/'protocol.json'),outcome=outcome,initial_candidate=read(run/'shared_initial.json'),
        core_candidate=read(run/'core/frozen_candidate.json'),core=core,
        arms={a:read(run/'arms'/a/'summary.json',{'status':'not_executed'}) for a in ('A','B','C','D')},
        strict_witnesses=witnesses,search_comparison=read(run/'search/corrected_comparison.json'),
        independent=tests,freeze_checks=freezes,cost=cost,
        core_chain=dict(status='verified_for_two_obligations_on_recorded_scope' if chain else 'not_established',passed=chain,
            independent_two_obligations=projected,scope='order_payload and finite drain_no_loss only; historical finite replay preserved; no global guarantee'),
        whole_parent_case=dict(passed=False,status='not_established',required_obligations=list(ALL_OBLIGATIONS),
            original_historical_fifo_bug='unknown',stat='unknown',engineering_parent_count=1,
            reason='This bounded run does not demonstrate complete protection of all obligations or original historical defect reproduction.'))
    result['accepted_obligation_mapping']={'core':accepted_mapping(run,'core',core),
        **{a:accepted_mapping(run,'arms/'+a,result['arms'][a]) for a in ('A','B','C','D')}}
    dump(out/'results.json',result);dump(out/'cost/results.json',cost);dump(out/'freeze_checks.json',freezes)
    (out/'REPORT.md').write_text(render(run,result),encoding='utf-8')
    shutil.copy2(__file__,out/'report_script_snapshot.py')
    manifest={p.relative_to(run).as_posix():digest(p) for p in files}
    dump(out/'manifest.json',manifest)
    sources={k:v for k,v in manifest.items() if Path(k).suffix in ('.py','.sv','.v')}
    dump(out/'source_and_rtl_hashes.json',sources)
    print(json.dumps(dict(status=result['status'],core_chain=chain,model_calls=cost['total']['model_calls'],
        native_compiles=cost['total']['native_compile_calls'],native_executes=cost['total']['native_execute_calls'],
        manifest_files=len(manifest),report=str(out/'REPORT.md'))))


if __name__=='__main__':main()
