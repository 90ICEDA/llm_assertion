"""Audit fresh pilot/replications after all terminal generation; never feedback."""
import argparse
import json
from pathlib import Path
import shutil

import research17_loop as loop
import research41_fresh_campaign as campaign
from research34_applicability import portable
from research34_campaign import digest
from research37_audit import audit as audit_child
from research17_report import artifacts,cost_audit

read,dump=loop.read,loop.dump


def report(run,out):
    terminal=read(run/'outcome.json')
    out.mkdir(parents=True,exist_ok=False)
    prep=portable(read(run/'prepared_source.json')['path'])
    checks=[]
    def check(name,value): checks.append(dict(name=name,passed=bool(value)))
    check('research40_preserved',campaign.protected_manifest()==read(prep/'protected_research40.json'))
    check('bounded_calls',terminal['calls']<=read(run/'authorization.json')['authorized_calls'])
    results={}
    proposals=[]
    for seed in (campaign.PILOT,*campaign.REPLICATIONS):
        child=run/f's{seed}'
        if not (child/'outcome.json').exists():
            results[str(seed)]=dict(status='not_executed',passed=None);continue
        outcome=read(child/'outcome.json')
        if (outcome['accepted'] or seed!=campaign.PILOT) and not (child/'independent/summary.json').exists():
            results[str(seed)]=dict(status='independent_not_completed',outcome=outcome,passed=None);continue
        child_out=out/f's{seed}';audit_child(child,child_out)
        verified=read(child_out/'results.json')
        check(f's{seed}:child_audit',verified['passed'])
        for name in ('research41_fresh_campaign.py','research38_history_feedback.py',
                     'research35_campaign.py','research40_interface_continuation.py',
                     'research15_native_interface.py','research31_gate.py',
                     'research34_applicability.py','research32_runtime.py'):
            check(f's{seed}:fixed_experiment_code:{name}',
                  digest(child/'source_snapshot'/name)==digest(prep/'source_snapshot'/name))
        check(f's{seed}:fresh_real_calls',1<=outcome['calls']<=2)
        first=read(child/'core/v0/model_call/request.json')
        check(f's{seed}:sealed_request',first==read(prep/f's{seed}/request.preview.json'))
        check(f's{seed}:sampling_parameters',first['seed']==seed and first['temperature']==0.2)
        for version in sorted((child/'core').glob('v*')):
            edit_path=version/'model_call/model_edit.json'
            if edit_path.exists():
                edit=read(edit_path)
                expression_record={k:edit.get(k) for k in ('operation','assertion_id','assertions')}
                proposals.append(dict(seed=seed,iteration=version.name,
                    expression_structure_sha256=loop.sha(expression_record),
                    decision=read(version/'decision.json'),source=str(edit_path)))
        independent=verified['independent']
        results[str(seed)]=dict(status=outcome['status'],accepted=outcome['accepted'],
            passed=bool(outcome['accepted'] and independent and independent['all_five_pass_on_first_attributed_evidence']),
            calls=outcome['calls'],cost=verified['cost'],history=verified['history'],
            independent=independent,hash=outcome['frozen_hash'])
    replicated=[s for s in campaign.REPLICATIONS if results[str(s)]['status']!='not_executed']
    if replicated:
        check('pilot_qualified_before_replications',results[str(campaign.PILOT)]['passed'])
        pilot_split=read(run/f's{campaign.PILOT}/independent/split.json')
        old_hashes=campaign.split_hashes(read(campaign.PROTECTED/'independent/split.json'))|campaign.split_hashes(pilot_split)
        check('all_three_ran',len(replicated)==3)
        batches=[]
        for seed in replicated:
            split=read(run/f's{seed}/independent/split.json')
            batches.append({k:split[k] for k in ('seed','boundary_cases','drain_cases')})
            check(f's{seed}:old_test_excluded',not campaign.split_hashes(split)&old_hashes)
        check('common_new_test_batch',all(b==batches[0] for b in batches))
        first_test=min((run/f's{s}/independent/split.json').stat().st_mtime for s in replicated)
        check('all_frozen_before_any_replication_test',all((run/f's{s}/core/freeze.json').stat().st_mtime<=first_test for s in replicated))
        check('all_model_calls_before_replication_test',all(p.stat().st_mtime<=first_test
            for s in replicated for p in (run/f's{s}/core').glob('v*/model_call/attempt.json')))
        # Same prompt/background, only requested seed differs. Pilot outputs and
        # test results cannot be used to adjust later first-round requests.
        messages=[read(prep/f's{s}/request.preview.json')['messages'] for s in (campaign.PILOT,*campaign.REPLICATIONS)]
        check('same_public_initial_information',all(m==messages[0] for m in messages))
    else:
        check('no_silent_stage2_success',terminal['status']!='pilot_and_three_seed_replications_completed')
    cost=cost_audit(run,artifacts(run))
    check('cost_calls',cost['total']['model_calls']==terminal['calls'])
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,terminal=terminal,
        seeds=results,pilot_in_replication_denominator=False,
        planned_replications=3,executed_replications=len(replicated),
        successful_replications=sum(results[str(s)].get('passed') is True for s in campaign.REPLICATIONS),
        cost=cost['total'],proposals=proposals,
        distinct_replication_expression_structures=len({p['expression_structure_sha256'] for p in proposals if p['seed'] in campaign.REPLICATIONS}),
        distinct_accepted_replication_expression_structures=len({p['expression_structure_sha256'] for p in proposals if p['seed'] in campaign.REPLICATIONS and p['decision']['accepted']}),
        first_call_successful_replications=sum(results[str(s)].get('passed') is True and results[str(s)].get('calls')==1 for s in campaign.REPLICATIONS),
        limit='Three requested seeds at temperature 0.2; provider seed control not independently verified. Finite first-attribution scope only.')
    dump(out/'results.json',result);dump(out/'cost.json',cost)
    dump(out/'task_matrix.json',dict(
        fresh_generation=dict(passed=results[str(campaign.PILOT)].get('passed') is True,
            evidence=f's{campaign.PILOT}/results.json',
            scope='Fresh real response under the interface fixed before this run; native target, history and fresh test.'),
        replications=dict(planned=3,executed=len(replicated),passed=result['successful_replications'],
            scope='Same public initial candidate and messages; requested provider seeds, not verified independent randomness.'),
        independent=dict(pilot_separate=True,replications_share_one_batch=True,
            scope='Do not multiply unique test inputs by number of candidate evaluations. Five obligations on first-attributed finite evidence; later unknown retained.'),
        remaining=['Controlled mechanism benefit is not established by this generation replication.',
                   'Real historical parent bug closure is not established by injected FIFO faults.',
                   'Full-timeline protection and general model reliability are not established.']))
    dump(out/'run_manifest.json',{p.relative_to(run).as_posix():digest(p) for p in artifacts(run)})
    shutil.copy2(__file__,out/'audit_source.py')
    traces=['# 实际自动细化轨迹', '',
        '开发漏报来自既有契约搜索，本轮复用其有效见证，不把再次回放计作新搜索发现。以下性质由原生包装器提供时钟和 disable iff(rst)。', '']
    for seed in (campaign.PILOT,campaign.REPLICATIONS[-1]):
        r=results[str(seed)]
        if not r.get('accepted'): continue
        child=run/f's{seed}'
        verified=read(out/f's{seed}/results.json')
        initial=read(prep/f's{seed}/shared_initial.json')
        frozen=read(child/'core/frozen_candidate.json')
        traces += [f'## 种子 {seed}', '']
        for edit in verified['edits']:
            traces += [f"模型版本 {edit['iteration']}：接受 {edit['decision']['accepted']}；拒绝原因 "
                       +json.dumps(edit['decision']['reasons'],ensure_ascii=False), '']
            if not edit['decision']['accepted']: continue
            aid=edit['edit']['assertion_id']
            traces += ['原始 SVA：','```systemverilog',
                next(a['property'] for a in initial['assertions'] if a['id']==aid),'```',
                '真实模型细化后的 SVA：','```systemverilog',
                next(a['property'] for a in frozen['assertions'] if a['id']==aid),'```','']
            rows=edit['target_gate']['target_rows']
            traces += [f'原先遗漏的 {len(rows)} 条目标均通过触发与因果检出检查。以下两条来自实际原生采样：','',
                '|证据 ID|前件周期|检查周期|触发|失败|因果检出|',
                '|---|---:|---:|---|---|---|']
            for row in rows[:2]:
                a=row['edited_assertion']
                traces.append(f"|{row['evidence_id']}|{row['native_antecedent_cycle']}|{row['check_cycle']}|{a['trigger']}|{a['failed']}|{a['causal_detection']}|")
        traces += ['', '历史回放：'+json.dumps(verified['history'],ensure_ascii=False),
            '冻结哈希：`'+r['hash']+'`。',
            '独立测试计数：'+json.dumps(verified['independent']['metrics']['counts'],ensure_ascii=False),
            f'完整前后证据见 `s{seed}/case_examples.json`；模型原响应、事务与波形保留在运行目录 `s{seed}/core/`。','']
    (out/'CASE_TRACES.md').write_text('\n'.join(traces)+'\n',encoding='utf-8')
    lines=['# research41：新接口真实细化与多种子复现','',
        f"运行状态 `{terminal['status']}`，记录检查通过 {sum(c['passed'] for c in checks)}/{len(checks)}。",'',
        '沿用已确认的13窗口事件计划及仍有8条漏报的公共候选。所有提案来自本轮真实调用，接口和接受门控在运行前固定。research40成功SVA和独立样本不进入请求；原冻结版本与结果保持。','',
        '| 种子 | 角色 | 调用 | 接受 | 五义务独立验收 |','|---|---|---:|---|---|']
    for seed,r in results.items():
        lines.append(f"| {seed} | {'先导' if int(seed)==campaign.PILOT else '复现'} | {r.get('calls','未运行')} | {r.get('accepted','未知')} | {r.get('passed')} |")
    lines += ['',f"预定复现分母3，实际运行 {len(replicated)}，成功 {result['successful_replications']}；先导不混入复现成功率。",'',
        f"复现阶段实际不同表达式结构数 {result['distinct_replication_expression_structures']}（忽略 reason；不是语义等价类数量）。请求 seed 不等于已证实服务端随机性，重复相同输出不算多个独立算法发现。",'',
        f"首轮即通过完整验收的复现 {result['first_call_successful_replications']}/3；被接受的复现表达式结构数 {result['distinct_accepted_replication_expression_structures']}。拒绝后第二轮成功计入有界细化结果，不混入首轮成功率。",'',
        '若第1项先导未通过，后续种子不执行，不能把未执行计作成功或当作已完成的稳定性实验。失败版本仍保留；执行多种子时，全部冻结后同一批新测试同时评估接受和保留版本。','',
        '成本：','```json',json.dumps(cost['total'],ensure_ascii=False,indent=2),'```','',
        '全部详细修改、目标与历史回放、独立五义务分母及后续归因unknown见各种子子报告。有限证据上的通过不是形式化证明或全局防退化；不能凭3个请求种子推断普遍稳定性。', '',
        '三个复现候选共用一批新测试，不将相同输入重复计算为三份独立样本。本轮不是新的四组机制消融，也不是新增真实历史父Bug。', '',
        '实际执行命令（运行目录已存在，不覆盖；新实验需要新的预算绑定）：', '```powershell',
        f'wsl -- python3 scripts/research41_fresh_campaign.py run --prepared {prep.relative_to(loop.ROOT).as_posix()} --out {run.relative_to(loop.ROOT).as_posix()} --authorization {prep.relative_to(loop.ROOT).as_posix()}/authorization.json', '```', '',
        '只读复核，无模型调用或新仿真；输出目录须不存在：', '```powershell',
        f'wsl -- python3 scripts/research41_report.py --run {run.relative_to(loop.ROOT).as_posix()} --out deliverables/research41_report_NEW', '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('FRESH_CAMPAIGN_AUDIT',result['passed'],flush=True)
    assert result['passed']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report(a.run.resolve(),a.out.resolve())
