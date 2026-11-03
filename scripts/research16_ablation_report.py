"""Summarize actually recorded runs, never synthesize successful outcomes."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import shutil

from research15_acceptance import inspect, sha
import research16_ablation as run

ROOT=run.ROOT


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='research16_ablation_20261016_r01');args=p.parse_args()
    base=ROOT/'deliverables'/args.run
    out=base/'report';out.mkdir(exist_ok=False)
    read=run.read
    def dump(name,value):run.dump(out/name,value)
    calls=[]
    for path in sorted(base.rglob('transport_result.json')):
        r=read(path)
        calls.append(dict(path=str(path.relative_to(ROOT)),**r))
    commands=[]
    for name in ('compile.json','execute.json'):
        for path in sorted(base.rglob(name)):
            if 'obj_dir' in path.parts:continue
            r=read(path);commands.append(dict(path=str(path.relative_to(ROOT)),kind=name[:-5],**r))
    total=dict(model_calls=sum(c['model_calls'] for c in calls),
        prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
        completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
        usage_unavailable_calls=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),
        model_wall_seconds=sum(c.get('wall_seconds',0) for c in calls),
        retries=sum(c.get('retries',0) for c in calls),formal_calls=0,monetary_cost=None,
        compile_calls=sum(c['kind']=='compile' for c in commands),
        simulation_calls=sum(c['kind']=='execute' for c in commands),
        compile_seconds=sum(c['wall_seconds'] for c in commands if c['kind']=='compile'),
        simulation_seconds=sum(c['wall_seconds'] for c in commands if c['kind']=='execute'))
    dump('costs.json',dict(totals=total,model_calls=calls,physical_commands=commands,
        note='Known token sums exclude unavailable usage; all compile bootstrap simulations and rejected proposal replays included. Search acquisition is shared by B/D, not charged twice.'))
    summaries={};mappings={};example={};checks=[];family_results={}
    for arm in run.experiment.ARMS:
        folder=base/'arms'/arm
        if not (folder/'summary.json').exists():continue
        s=read(folder/'summary.json');frozen=read(folder/'frozen_candidate.json');freeze=read(folder/'freeze.json')
        checks.append(dict(check='frozen_hash',arm=arm,passed=sha(frozen)==freeze['candidate_sha256'] and digest(folder/'frozen_candidate.sva')==freeze['sva_sha256']))
        hold=base/'holdout'/arm/'ledger.json'
        held=inspect(read(hold)['ledger']) if hold.exists() else None
        counts={k:len(held[k]) for k in ('rows','unknown','false_positives','detections','misses','triggers')} if held else None
        target_count=sum(r['oracle']['verdict']=='violated' for r in held['rows'].values()) if held else None
        summaries[arm]=dict(config=s['config'],accepted_proposal=s['decision']['accepted'],decision=s['decision'],
            selected_version=freeze['selected_version'],before=s['before'],proposed_after=s['after'],
            proposal_frontend_status=s['call'].get('candidate_status','unavailable'),
            proposal_frontend_error=s['call'].get('candidate_error'),
            proposal_compile_status=read(folder/'compiled/result.json')['compile_status'] if (folder/'compiled/result.json').exists() else 'not_run',
            holdout=counts,holdout_target_rows=target_count,
            holdout_later_attribution_unknown=len(read(hold).get('exclusions',[])) if hold.exists() else None,
            model_call=s['call'])
        mappings[arm]={}
        if held:
            for obligation in run.runtime.OBLIGATIONS:
                rows=[r for r in held['rows'].values() if r['obligation']==obligation]
                ob=inspect(rows)
                mappings[arm][obligation]=dict(counts={k:len(ob[k]) for k in ('rows','unknown','false_positives','detections','misses','triggers')},
                    target_rows=sum(r['oracle']['verdict']=='violated' for r in rows),mapping=ob['mapping'])
            family_results[arm]={}
            for family in ('random','tail_loss','reset_pending'):
                selected=[r for r in held['rows'].values() if r.get('scenario_id','').endswith(':'+family)]
                scoped=inspect(selected)
                family_results[arm][family]={k:len(scoped[k]) for k in ('rows','unknown','false_positives','detections','misses','triggers')}
            # A narrowly stated primary treatment endpoint, alongside the
            # complete test results. Never substitute it for whole-case pass.
            selected=[r for r in held['rows'].values() if r.get('scenario_id','').endswith(':tail_loss')
                      and r['variant'] in ('correct','drop') and r['obligation'] in ('order_payload','drain_no_loss')]
            scoped=inspect(selected)
            family_results[arm]['primary_tail_loss_correct_drop_order_drain']={k:len(scoped[k]) for k in ('rows','unknown','false_positives','detections','misses','triggers')}
        example[arm]=dict(proposed_sva=(folder/'model_call/candidate.sva').read_text() if (folder/'model_call/candidate.sva').exists() else None,
            final_sva=(folder/'frozen_candidate.sva').read_text(),decision=s['decision'],historical_gate=read(folder/'historical_gate_audit.json') if (folder/'historical_gate_audit.json').exists() else None)
    dump('arms.json',summaries);dump('obligation_mapping.json',mappings);dump('holdout_families.json',family_results)
    shared=read(base/'shared_initial.json') if (base/'shared_initial.json').exists() else None
    witness=read(base/'search/treatment_witness.json') if (base/'search/treatment_witness.json').exists() else None
    if shared:
        example['initial_sva']=run.interface.candidate_sva(shared)
    example['actual_search_witness']=witness
    dump('trajectories.json',example)
    if len(summaries)==4:
        requests={a:read(base/'arms'/a/'model_call/request.json') for a in summaries}
        contexts={a:json.loads(r['messages'][1]['content']) for a,r in requests.items()}
        checks.append(dict(check='same_model_and_sampling_options',passed=len({json.dumps([r['model'],r['options']],sort_keys=True) for r in requests.values()})==1))
        from research16_ablation_refine import structured_existing
        checks.append(dict(check='same_initial_candidate',passed=all(c['current_assertions'] in (shared,structured_existing(shared)) for c in contexts.values())))
        variable={'current_assertions','counts','issues','task','acquired_new_evidence'}
        checks.append(dict(check='same_public_background',passed=len({json.dumps({k:v for k,v in c.items() if k not in variable},sort_keys=True) for c in contexts.values()})==1))
        checks.append(dict(check='only_B_D_mark_acquired_evidence',passed=all(c['acquired_new_evidence']==(a in ('B','D')) for a,c in contexts.items())))
        checks.append(dict(check='identical_prompts_within_search_level',passed=requests['A']['messages']==requests['C']['messages'] and requests['B']['messages']==requests['D']['messages']))
        if witness:
            checks.append(dict(check='witness_bound_to_initial_bytes',passed=witness['initial_candidate_sha256']==digest(base/'shared_initial.json')))
        for a in ('A','C'):
            before=read(base/'arms'/a/'before_ledger.json')
            checks.append(dict(check='no_search_rows_in_control_ledger',arm=a,passed=all(r['scenario_id'].startswith('common:') for r in before['ledger'])))
        if (base/'holdout/summary.json').exists():
            protocol=read(base/'protocol.json')
            checks.append(dict(check='test_bound_to_all_arm_freeze',passed=protocol['all_arms_freeze_file_sha256']==digest(base/'all_arms_freeze.json')))
            test_seeds={c['seed'] for c in protocol['holdout']}
            checks.append(dict(check='test_seeds_distinct_from_development_schedules',passed=not test_seeds & ({2026101501}|{s+q*1009 for s in (2026101507,2026101531) for q in range(6)})))
    # Verify previous sealed evidence remains unmodified.
    for bundle,filename in [('research_integration_20261014_r01','delivery_manifest.json'),('research15_integration_20261015_r01','delivery_manifest.json'),('historical_record_recovery_20261015_r01','manifest.json')]:
        manifest=read(ROOT/'deliverables'/bundle/filename)
        checks.append(dict(check='old_bundle_unchanged',bundle=bundle,files=len(manifest),passed=all((ROOT/p).is_file() and digest(ROOT/p)==h for p,h in manifest.items())))
    dump('audit_checks.json',checks)
    finished=len(summaries)==4 and all(s['holdout'] is not None for s in summaries.values())
    status=dict(four_arm_experiment_executed=finished,successful_mechanism_chain_established=False,
        initial_qualified=shared is not None,treatment_found=witness is not None,actual_completed_arms=len(summaries),
        integrity_checks_passed=all(c['passed'] for c in checks),scope='One model seed and one artificial FIFO fault family; success or null effects must be read from actual arm outcomes.',
        next_action='Interpret arm results; do not modify frozen assertions from held-out failures.' if finished else 'See blocked stages and original records; no four-arm success claim.')
    # A bounded successful chain requires search proposal admission, retained
    # common protection, no held-out FP/unknown/miss, and actual drain detection.
    d=summaries.get('D',{})
    status['scoped_tail_loss_chain_established']=False
    if finished and d.get('accepted_proposal'):
        h=d['holdout'];drain=mappings['D']['drain_no_loss']['counts']
        status['successful_mechanism_chain_established']=not any(h[k] for k in ('unknown','false_positives','misses')) and drain['detections']>0
        primary=family_results['D']['primary_tail_loss_correct_drop_order_drain']
        status['scoped_tail_loss_chain_established']=bool(example['D']['historical_gate']['accepted'] and witness
            and not any(primary[k] for k in ('unknown','false_positives','misses')) and primary['detections']>0)
    dump('status.json',status)
    lines=['# 四组机制消融实际运行报告','',
        f"四组执行与冻结后测试完成：{finished}。完整范围成功证据链成立：{status['successful_mechanism_chain_established']}。",'',
        '本轮复用原生Verilator运行器、独立事务oracle、四法搜索和义务接受门。SVA来自真实本地模型：接口按plan.json记录，自由文本或结构化前件/后件/时序枚举；后者只做通用语法组装，不手工修改谓词或时序。所有故障为实际axis_fifo外围人工故障，不计作上游历史FIFO缺陷。', '',
        '| 组 | 搜索 | 防退化门 | 修改接受 | 独立FP | 独立检出 | 独立漏检 | 独立unknown |', '|---|---|---|---|---:|---:|---:|---:|']
    for a,s in summaries.items():
        h=s['holdout'] or {}
        lines.append(f"| {a} | {s['config']['search']} | {s['config']['gate']} | {s['accepted_proposal']} | {h.get('false_positives','未运行')} | {h.get('detections','未运行')} | {h.get('misses','未运行')} | {h.get('unknown','未运行')} |")
    lines += ['', '计数为去重后的义务×采样周期证据行，不是独立Bug。每个复位epoch只将首次oracle违例作为可归因目标；后续违例另存unknown排除记录。具体分母、每条义务、触发及全部历史门理由见arms.json和obligation_mapping.json。',
        f"处理目标的局部证据链成立：{status['scoped_tail_loss_chain_established']}；仅指独立tail_loss场景下correct/drop两版本的order_payload与drain_no_loss，以及开发历史接受门通过。其余义务、故障和unknown仍按完整测试报告，不能用局部改善替代案例完整成功。", '',
        '## 实际轨迹', '', '初始模型SVA：', '```systemverilog',example.get('initial_sva','未获得合格初始版本'),'```']
    if witness:
        lines += ['', '搜索见证：'+json.dumps(witness['first_violation'],ensure_ascii=False),
                  '见证来源：'+witness['source_query_directory']]
    for a in ('B','D'):
        if a in example:
            lines += ['', f'组{a}模型提案：','```systemverilog',example[a]['proposed_sva'] or '模型未产生可解析候选','```',
                      '接受判定：'+json.dumps(example[a]['decision'],ensure_ascii=False)]
    lines += ['', '## 成本与范围', '', json.dumps(total,ensure_ascii=False),
        '', '每组最多一次模型修改，公共初始化和实际搜索成本另列。B/D共享同一次见证获取，搜索成本不重复计算；无搜索组没有该开销，因此总预算不完全相等。token差异来自真实提示与输出长度，未填充调用以伪造等成本。',
        '独立输入只在四组冻结后生成；使用同一已知生成语法的新随机种子及depth4/pipeline2。没有在看到独立结果后修改SVA。该小规模实验不能证明普遍优势、全局无退化或形式正确。',
        '接受门效果需要有实际会退化的提案才能观察；如果门开关两组选择相同，属于未观察到效果，不是防退化已被证明必要。', '',
        '## 复现', '', '在仓库根目录执行，RUN必须是新目录名。r03需先有未查看独立测试的源实验，详见reused_evidence.json；已测试源实验不能用来重复声称预测试准备：', '```powershell',
        *([f'wsl -- python3 scripts/research16_ablation_refine.py {stage} --run RUN --source SOURCE' for stage in ('prepare','baseline','arms','holdout')] if (base/'reused_evidence.json').exists() else [f'wsl -- python3 scripts/research16_ablation.py {stage} --run RUN' for stage in ('prepare','initial','search','baseline','arms','holdout')]),
        'wsl -- python3 scripts/research16_ablation_report.py --run RUN','```',
        '', '前置阶段失败时应保留失败结果；不得跳过资格检查或替换为手写断言。', '']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    shutil.copy2(__file__,out/'report_script_snapshot.py')
    # Include original model responses, waves, code and trace artifacts, omit
    # reproducible compiler intermediates only; no old artifacts are modified.
    manifest={str(p.relative_to(base)):digest(p) for p in sorted(base.rglob('*'))
              if p.is_file() and 'obj_dir' not in p.parts and '__pycache__' not in p.parts and p.name!='manifest.json'}
    dump('manifest.json',manifest)
    print(json.dumps(dict(status=status,costs=total),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
