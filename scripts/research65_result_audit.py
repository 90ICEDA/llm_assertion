"""Post-run raw-log audit and interpretation; never changes sealed search selection."""
import argparse
import copy
from pathlib import Path
import research64_native_audit as native_audit
import research65_search_value as experiment

base=experiment.base


def main(root,out):
    native_audit.audit(root,out)
    experiment.report(root)
    summary=base.read(root/'summary.json'); totals=base.read(root/'method_totals.json')
    public=base.read(root/'public_feedback.json'); sensitivity=[]
    # Identical action at identical query/seed must use byte-identical stimulation,
    # regardless of which method selected it. Outcomes are not selector inputs.
    shared_inputs={}; matched_inputs=0
    for r in base.read(root/'records.json'):
        identity=(r['pair'],r['seed'],r['query'],r['family'],r['duration'])
        primary=r['pair'].split('__')[0]
        path=root/'queries'/r['pair']/f"s{r['seed']}"/r['method']/f"q{r['query']}"/primary/'correct_stimulus'/'stimulus.json'
        fingerprint=base.digest(path)
        if identity in shared_inputs:
            assert shared_inputs[identity]==fingerprint,identity
            matched_inputs+=1
        else:shared_inputs[identity]=fingerprint
    base.dump(out/'shared_input_audit.json',dict(matching_action_comparisons=matched_inputs,
        passed=True,identity='pair / seed / query / family / duration'))
    base.dump(out/'first_discovery_costs.json',[dict(pair=s['pair'],seed=s['seed'],method=s['method'],
        key=k,query=q,search_native_executions=16*q,shared_public_native_executions_per_pair=32,
        accounting='Public setup shared physically; common 3 builds/bootstrap executions reported separately.')
        for s in summary for k,q in s['first_query'].items()])
    for s in summary:
        if s['method']!='contract_novelty':continue
        p=experiment.policy.Acquisition('contract_novelty',s['seed'])
        for r in public[s['pair']]['results']:p.observe(r['family'],r)
        for q in range(base.BUDGET):
            folder=root/'queries'/s['pair']/f"s{s['seed']}"/'contract_novelty'/f'q{q}'
            before=copy.deepcopy(p); actual=p.choose()
            altered=copy.deepcopy(before);altered.exposed.clear()
            probe=altered.choose()
            sensitivity.append(dict(pair=s['pair'],seed=s['seed'],query=q,
                actual=[actual['family'],actual['duration']],
                without_confirmed_gap_retirement=[probe['family'],probe['duration']],
                selection_changed=(actual['family'],actual['duration'])!=(probe['family'],probe['duration']),
                scores_changed=actual['deficit_scores']!=probe['deficit_scores']))
            r=base.read(folder/'result.json');p.observe(r['family'],r)
    base.dump(out/'feedback_diagnostic.json',dict(rows=sensitivity,
        changed=sum(r['selection_changed'] for r in sensitivity),
        scope='Counterfactual selector-only audit on actual observed state; no native query or discovery credited.'))
    costs=base.read(root/'cost.json')['total']; audit=base.read(out/'audit.json')
    unions={m:set(t['keys']) for m,t in totals.items()}
    contrast=dict(extra_over_old=sorted(unions['contract_novelty']-unions['contract_coverage']),
                  lost_vs_old=sorted(unions['contract_coverage']-unions['contract_novelty']),
                  extra_over_generic=sorted(unions['contract_novelty']-unions['ordinary_no_repeat']),
                  lost_vs_generic=sorted(unions['ordinary_no_repeat']-unions['contract_novelty']),
                  extra_over_all=sorted(unions['contract_novelty']-set().union(*(s for m,s in unions.items() if m!='contract_novelty'))))
    base.dump(out/'conclusion.json',dict(contrasts=contrast,
        old_repeated_actions=totals['contract_coverage']['repeated_action_queries'],
        new_repeated_actions=totals['contract_novelty']['repeated_action_queries'],
        audit_passed=audit['passed'],policy_replay=base.read(root/'policy_audit.json'),
        no_global_advantage_claim=True,scope='One FIFO parent, artificial faults, development candidates, two seeds, depth4/pipeline1'))
    text=['# research65 选择轨迹与结果复核','',
        '旧策略把“性质尚未保护”混作“还需发现该缺口”的优先级。research64 中已曝光复位缺口后，no_unsolicited_output仍有4分；两个复位义务共用场景但独立折扣，导致重复。新策略保留保护缺口、送入细化队列，仅降低其发现优先级；场景族/背压时长作为动作身份，已用动作不再占本轮查询。',
        '', '这是一项有界探索取舍：同类场景换数据可能揭示其他问题；本轮不重试不等于这些输入已穷尽。新策略未修复断言，也不自动启动模型调用。', '',
        '|策略|去重候选缺口|重复动作|无新增缺口查询|后续归因unknown|',
        '|---|---:|---:|---:|---:|']
    for m,t in totals.items():text.append(f"|{m}|{t['unique_candidate_gaps']}|{t['repeated_action_queries']}|{t['zero_new_key_queries']}|{t['later_attribution_unknown']}|")
    text+=['',f"新契约比旧契约多{len(contrast['extra_over_old'])}个、少{len(contrast['lost_vs_old'])}个候选缺口；比普通不重复策略多{len(contrast['extra_over_generic'])}个、少{len(contrast['lost_vs_generic'])}个；超出全部对照并集{len(contrast['extra_over_all'])}个。缺口按候选哈希/误报或漏报/义务/故障机制去重，不是独立Bug数量。",
        '', '以下列出pre_valid主候选、种子6503的三种策略轨迹，作为事后说明例；不能用该例代替全部种子的比较，完整差集见contrasts.json：', '',
        '|策略|查询(从1起)|场景/时长|新增缺口|已确认待细化缺口数（查询前）|',
        '|---|---:|---|---|---:|']
    for s in summary:
        if s['pair']=='pre_valid__valid' and s['seed']==6503 and s['method'] in ('contract_coverage','contract_novelty','ordinary_no_repeat'):
            for r in s['selections']:
                keys=['/'.join(k.split('/')[1:]) for k in r['new_keys']]
                text.append(f"|{s['method']}|{r['query']+1}|{r['action']}|{', '.join(keys) or '无'}|{len(r['refinement_queue'])}|")
    calls=base.read(root/'reference_costs.json')
    text+=['',f"原始日志复核：{len(audit['checks'])}项，{audit['native_replays_verified']}次原生记录；策略重放42组/168次（实际值见policy_audit.json）。原生编译{costs['native_compile_calls']}、执行{costs['native_execute_calls']}，编译{costs['native_compile_wall_seconds']:.3f}秒、执行{costs['native_execute_wall_seconds']:.3f}秒；模型/tokens/形式化0。",'',
        '|参考计算|实验实际调用|实验墙钟秒|', '|---|---:|---:|']
    for k in ('transaction_reference','sampling_reference','paired_obligation_judge'):
        cc=[c for c in calls if c['kind']==k]
        text.append(f"|{k}|{len(cc)}|{sum(c['wall_seconds'] for c in cc):.6f}|")
    text+=['',f"审计额外重算单列：事务{audit['transaction_reference_calls']}、采样{audit['sampling_reference_calls']}、配对{audit['paired_judge_calls']}，参考计算{audit['reference_wall_seconds']:.6f}秒。不混入搜索收益或实验调用。",
        '', 'unknown未删去：关键判定、后续归因分别见summary.json。后续归因unknown不能当作无误报或全程保护；本轮发现仅计独立参考模型确认的首违例。所有查询未找到缺口也不等于证明正确。',
        '', '总体判断：重复动作消除与契约额外收益是两件事。对照结果、个别种子先发现及整体缺口并集均保留；不能只凭去重成功声称契约总体更优。下一步需其他候选/机制和更多预先固定种子，另验收与自动细化联动的防退化增量。',
        '', '复跑（新输出目录）：', '```powershell',
        'wsl -- python3 scripts/research65_search_value.py prepare --out deliverables/research65_NEW',
        'wsl -- python3 scripts/research65_search_value.py run --out deliverables/research65_NEW',
        'wsl -- python3 scripts/research65_result_audit.py --run deliverables/research65_NEW --out deliverables/research65_audit_NEW',
        '```', '', '现有协议、结果及逐条波形位于 '+str(root.relative_to(base.ROOT)).replace('\\','/')+'；旧research64结果保持不变。']
    (out/'SUMMARY.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    base.dump(out/'analysis_code_versions.json',{str(p.relative_to(base.ROOT)):base.digest(p) for p in (
        Path(__file__).resolve(),base.ROOT/'scripts/research64_native_audit.py')})
    print('FINAL',contrast,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args();main(a.run.resolve(),a.out.resolve())
