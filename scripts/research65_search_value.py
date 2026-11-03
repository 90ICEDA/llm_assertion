"""Preregistered acquisition-policy comparison reusing research64 native execution."""
import argparse
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import research64_search_value as base
import research65_search_policy as policy

SEEDS = (6503, 6521)
METHODS = base.METHODS + policy.NEW


@contextmanager
def installed():
    with patch.object(base.grammar, 'Policy', policy.factory), patch.multiple(
            base, SEEDS=SEEDS, METHODS=METHODS, decision=policy.decision,
            update=policy.update, report=report):
        yield


def prepare(out):
    checks = policy.tests()
    with installed():
        base.prepare(out)
    protocol = base.read(out/'protocol.json')
    protocol.update(experiment='research65',
        policy='contract_coverage unchanged research64 control. contract_novelty uses finite family/duration action pool, excludes executed public/search actions, queues confirmed keys for refinement, replaces exposed-obligation acquisition deficit with boundary exploration weight 1; other deficits and obligation attempt discount remain. Shared reset action cannot be retried under another obligation. Untried boundaries remain eligible. Unknown consumes an attempt but never confirms/clears an obligation. No claim of full protection.',
        generic_control='ordinary_no_repeat samples uniformly from the identical untried action pool, receives only executed family/duration, no oracle outcome. Separates generic novelty scheduling from contract-specific benefit.',
        action_pool=[list(a) for a in policy.ACTIONS],
        stopping='Four queries per arm, six available actions after two public actions. No rerun of identical action in new policies. Outside this protocol exhaustion stops with unspent budget; no forced repeated tests.',
        retrospective_origin='Policy developed from research64 repeated reset/tail choices. New seeds 6503/6521 fixed before execution. Same known development candidates/fault grammar, not independent generalization evidence.',
        hypotheses='Measure repeated action queries, zero-new-key queries, public-unexposed deduplicated keys and first discovery costs. Zero-new-key queries can still improve exposure, so not automatically wasted. Compare new contract to old contract AND generic no-repeat AND original baselines. No predetermined positive conclusion.',
        scope=protocol['scope']+' No assertion edits, model refinement or frozen independent acceptance in this experiment.')
    base.dump(out/'protocol.json', protocol)
    registry = base.read(out/'historical_registry.json')
    prior = base.ROOT/'deliverables/research64_search_value_20261023_r01/records.json'
    if prior.exists():
        keys = sorted({k for r in base.read(prior) for k in r['gap_keys']})
        registry['keys'] = sorted(set(registry['keys']) | set(keys))
        registry['mechanisms'] = sorted(set(registry['mechanisms']) | {'/'.join(k.split('/')[1:]) for k in keys})
        registry['sources'].append(dict(path=str(prior.relative_to(base.ROOT)), sha256=base.digest(prior), keys=keys))
    base.dump(out/'historical_registry.json', registry)
    base.dump(out/'local_checks.json', dict(passed=len(checks), checks=checks))
    base.dump(out/'sealed.json', {str(p.relative_to(out)):base.digest(p) for p in out.rglob('*')
              if p.is_file() and p.name not in ('sealed.json','outcome.json')})
    base.verify(out)
    print('SEALED', out, 'local_checks', len(checks), flush=True)


def report(out):
    base.verify(out)
    records=base.read(out/'records.json'); public=base.read(out/'public_feedback.json')
    assert base.digest(out/'public_feedback.json')==base.read(out/'public_freeze.json')['sha256']
    calls=base.read(out/'reference_costs.json'); summary=[]
    historical=base.read(out/'historical_registry.json')
    for admission in base.read(out/'qualification.json'):
        if not admission['qualified']:continue
        pair=admission['pair']
        for seed in SEEDS:
            for method in METHODS:
                rr=[r for r in records if (r['pair'],r['seed'],r['method'])==(pair,seed,method)]
                assert len(rr)==base.BUDGET
                p=policy.factory(method if method!='coverage_sweep' else 'ordinary',seed)
                history=[]; seen=set(public[pair]['gap_keys']); actions=set(); repeats=0; first={}; row=[]
                for r in public[pair]['results']:
                    history.append(policy.update(p,method,r['family'],r));actions.add((r['family'],r['duration']))
                for q,r in enumerate(rr):
                    chosen=policy.decision(p,method,seed,q,history)
                    selection=base.read(out/'queries'/pair/f's{seed}'/method/f'q{q}'/'selection.json')
                    assert chosen==selection['chosen'] and history==selection['permitted_history']
                    assert r['first_new_keys']==sorted(set(r['gap_keys'])-seen)
                    assert r['public_unexposed_keys']==sorted(set(r['gap_keys'])-set(public[pair]['gap_keys']))
                    action=(r['family'],r['duration']); repeated=action in actions
                    repeats+=repeated;actions.add(action);seen.update(r['gap_keys'])
                    for k in r['first_new_keys']:first[k]=q+1
                    row.append(dict(query=q,action=action,repeated_action=repeated,new_keys=r['first_new_keys'],
                                    target=chosen.get('target_obligations',chosen.get('target_obligation')),
                                    refinement_queue=chosen.get('refinement_queue',[])))
                    history.append(policy.update(p,method,r['family'],r))
                if method in policy.NEW:assert repeats==0
                cc=[c for c in calls if (c.get('pair'),c.get('seed'),c.get('method'))==(pair,seed,method)]
                summary.append(dict(pair=pair,seed=seed,method=method,queries=len(rr),
                    new_keys=sorted(first),first_query=first,repeated_action_queries=repeats,
                    zero_new_key_queries=sum(not r['first_new_keys'] for r in rr),
                    repeated_observations=sum(r['repeated_observations'] for r in rr),
                    unknown=sum(r['unknown'] for r in rr),later_attribution_unknown=sum(r['later_attribution_unknown'] for r in rr),
                    failed_queries=sum(not r['healthy'] for r in rr),native_executions=sum(r['native_executions'] for r in rr),
                    reference_cost={kind:dict(calls=sum(c['kind']==kind for c in cc),wall_seconds=sum(c['wall_seconds'] for c in cc if c['kind']==kind)) for kind in ('transaction_reference','sampling_reference','paired_obligation_judge')},
                    selector_seconds=sum(r['selector_seconds'] for r in rr),
                    query_wall_seconds=sum(r['query_wall_seconds'] for r in rr),selections=row,
                    final_refinement_queue=sorted(p.refinement) if method in policy.NEW else None,
                    historical_novelty={k:'historically_known_same_candidate' if k in historical['keys'] else 'unknown_partial_history' for k in first}))
    totals={}
    for method in METHODS:
        ss=[s for s in summary if s['method']==method]
        keys=sorted({k for s in ss for k in s['new_keys']})
        totals[method]=dict(keys=keys,unique_candidate_gaps=len(keys),
            unique_mechanisms=len({'/'.join(k.split('/')[1:]) for k in keys}),
            **{k:sum(s[k] for s in ss) for k in ('queries','native_executions','repeated_action_queries',
               'zero_new_key_queries','repeated_observations','unknown','later_attribution_unknown','failed_queries')})
    contrasts=[]
    for pair in public:
        for seed in SEEDS:
            ss={s['method']:s for s in summary if s['pair']==pair and s['seed']==seed}
            if not ss:continue
            for method in METHODS:
                new,other=ss['contract_novelty'],ss[method]
                contrasts.append(dict(pair=pair,seed=seed,comparator=method,
                    new_only=sorted(set(new['new_keys'])-set(other['new_keys'])),
                    comparator_only=sorted(set(other['new_keys'])-set(new['new_keys'])),
                    first_query=[dict(key=k,new=new['first_query'].get(k),comparator=other['first_query'].get(k))
                                 for k in sorted(set(new['new_keys'])|set(other['new_keys']))]))
    costs=base.native_cost(out)
    assert costs['total']['native_execute_calls']==len(records)*16+99
    base.dump(out/'summary.json',summary);base.dump(out/'method_totals.json',totals)
    base.dump(out/'contrasts.json',contrasts);base.dump(out/'cost.json',costs)
    base.dump(out/'policy_audit.json',dict(groups=len(summary),queries=len(records),policy_replay_and_novelty=True))
    lines=['# research65：已曝光缺口与搜索预算','',
        '协议在执行前封存。3个有向候选任务、2个新固定种子、7种策略，各4次查询；同一公共反馈、候选、已知人工故障池及原生执行预算。全部为开发比较，不是独立验收。', '',
        '|策略|公共之外去重缺口|去候选后机制数|重复动作查询|无新增缺口查询|查询数|',
        '|---|---:|---:|---:|---:|---:|']
    for m,t in totals.items():lines.append(f"|{m}|{t['unique_candidate_gaps']}|{t['unique_mechanisms']}|{t['repeated_action_queries']}|{t['zero_new_key_queries']}|{t['queries']}|")
    extra=set(totals['contract_novelty']['keys'])-set().union(*(set(totals[m]['keys']) for m in METHODS if m!='contract_novelty'))
    lines+=['',f'新契约策略在全部对照并集之外的候选缺口数：{len(extra)}。逐任务/种子额外发现及丢失、首次发现查询见 contrasts.json。不得把方法并集或个别种子的早发现等同稳定优势。',
        '', '重复动作指已执行过相同场景族及背压时长（包括公共输入），不代表激励字节相同。无新增缺口不自动等于浪费：仍可能提供新的曝光或确认。新策略将已确认缺口排入细化队列，不宣称义务已保护；未试边界保留、unknown不视为已解决。',
        '',f"原生编译/执行实际次数：{costs['total']['native_compile_calls']}/{costs['total']['native_execute_calls']}；模型调用、tokens、形式化查询均0。完整原生耗时见cost.json，参考模型/采样/事务判定逐次成本见reference_costs.json，选择成本及后续归因unknown见summary.json。额外日志审计成本单列。",
        '', '公共之外新颖性仅相对本次公共反馈；历史索引命中注明已知，未命中保留unknown。所有故障均已有人工变异，不能报告为新历史Bug。未修改既有SVA或旧实验结果，未读取独立测试。',
        '', '复核命令：`wsl -- python3 scripts/research65_search_value.py report --out '+str(out.relative_to(base.ROOT)).replace('\\','/')+'`']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('REPORT', {m:t['unique_candidate_gaps'] for m,t in totals.items()},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['test','prepare','run','report'])
    parser.add_argument('--out',type=Path)
    a=parser.parse_args()
    if a.action=='test':print('PASS',len(policy.tests()))
    elif a.action=='run':
        with installed():base.run(a.out.resolve())
    else:globals()[a.action](a.out.resolve())
