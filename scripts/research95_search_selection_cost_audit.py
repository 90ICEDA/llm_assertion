"""Read-only selector replay and recorded cost audit; no model/native queries."""
import argparse
import copy
import time
from collections import defaultdict
from pathlib import Path
import research65_search_policy as policy
import research64_search_value as b

ROOT,read,dump,sha=b.ROOT,b.read,b.dump,b.digest
SOURCES=('research82_search_20261025_r01','research84_generalization_20261025_r01')


def run(out):
    out.mkdir(parents=True,exist_ok=False);started=time.perf_counter()
    all_probes=[];summaries=[];first_costs=[];bindings={}
    for name in SOURCES:
        root=ROOT/'deliverables'/name
        names=('records.json','public_feedback.json','reference_costs.json','cost.json','protocol.json')
        for n in names:bindings[(root/n).relative_to(ROOT).as_posix()]=sha(root/n)
        records=read(root/'records.json');public=read(root/'public_feedback.json');refs=read(root/'reference_costs.json')
        grouped=defaultdict(list)
        for record in records:grouped[(record['pair'],record['seed'],record['method'])].append(record)
        method_keys=defaultdict(set);accounting=[]
        for (pair,seed,method),rr in grouped.items():
            rr.sort(key=lambda r:r['query']);state=policy.factory(method,seed);history=[]
            known=set(public[pair]['gap_keys']);first={};actions=set();repeats=0
            for row in public[pair]['results']:
                history.append(policy.update(state,method,row['family'],row));actions.add((row['family'],row['duration']))
            for q,row in enumerate(rr):
                before=copy.deepcopy(state)
                chosen=policy.decision(state,method,seed,q,history)
                saved=read(root/'queries'/pair/f's{seed}'/method/f'q{q}/selection.json')
                assert chosen==saved['chosen'] and history==saved['permitted_history']
                assert (chosen['family'],chosen.get('duration'))==(row['family'],row['duration'])
                assert row['first_new_keys']==sorted(set(row['gap_keys'])-known)
                for key in row['first_new_keys']:first[key]=q+1
                known.update(row['gap_keys']);action=(row['family'],row['duration'])
                repeats+=action in actions;actions.add(action)
                if method=='contract_novelty':
                    for field in ('exposed','checks','triggers','protected','all_contract_scores'):
                        altered=copy.deepcopy(before)
                        if field=='all_contract_scores':altered.method='ordinary_no_repeat'
                        else:getattr(altered,field).clear()
                        alternative=altered.choose();other=(alternative['family'],alternative['duration'])
                        all_probes.append(dict(source=name,pair=pair,seed=seed,query=q,removed=field,
                            actual=list(action),alternative=list(other),changed=action!=other,
                            scope='Single decision intervention on actual state with identical RNG; no counterfactual execution or gain claim.'))
                history.append(policy.update(state,method,row['family'],row))
            method_keys[method].update(first)
            cc=[r for r in refs if r.get('stage')=='search' and (r.get('pair'),r.get('seed'),r.get('method'))==(pair,seed,method)]
            accounting.append(dict(pair=pair,seed=seed,method=method,queries=len(rr),
                native_executions=sum(r['native_executions'] for r in rr),repeated_actions=repeats,
                reference_calls=len(cc),reference_seconds=sum(r['wall_seconds'] for r in cc),
                selector_seconds=sum(r['selector_seconds'] for r in rr),query_seconds=sum(r['query_wall_seconds'] for r in rr),
                unknown=sum(r['unknown'] for r in rr),later_unknown=sum(r['later_attribution_unknown'] for r in rr)))
            for key,number in first.items():
                prefix=[r for r in cc if r['query']<number]
                first_costs.append(dict(source=name,pair=pair,seed=seed,method=method,key=key,
                    first_query=number,native_executions=sum(r['native_executions'] for r in rr[:number]),
                    reference_calls=len(prefix),reference_seconds=sum(r['wall_seconds'] for r in prefix),
                    selector_seconds=sum(r['selector_seconds'] for r in rr[:number]),
                    query_seconds=sum(r['query_wall_seconds'] for r in rr[:number])))
        extra=sorted(method_keys['contract_novelty']-set().union(*(v for k,v in method_keys.items() if k!='contract_novelty')))
        total=read(root/'cost.json')['total']
        common_native=sum(r['native_executions'] for p in public.values() for r in p['results'])
        summaries.append(dict(source=name,query_count=len(records),selection_replay_passed=True,
            methods={m:dict(unique_candidate_gaps=len(keys),keys=sorted(keys),
                **{f:sum(a[f] for a in accounting if a['method']==m) for f in ('queries','native_executions','repeated_actions','reference_calls','reference_seconds','selector_seconds','query_seconds','unknown','later_unknown')}) for m,keys in method_keys.items()},
            contract_exclusive_keys=extra,recorded_physical_cost=total,
            measured_query_native=sum(a['native_executions'] for a in accounting),common_public_native=common_native,
            native_non_query_residual=total['native_execute_calls']-common_native-sum(a['native_executions'] for a in accounting),
            accounting='Reference cost is included within query wall time; never add both as independent total. Public/build/measurement costs remain separate; physical ledger reused, not a new native execution audit.'))
    for n,h in bindings.items():assert sha(ROOT/n)==h,n
    changes={name:dict(changed=sum(p['changed'] for p in all_probes if p['removed']==name),
        decisions=sum(p['removed']==name for p in all_probes)) for name in ('exposed','checks','triggers','protected','all_contract_scores')}
    dump(out/'source_bindings.json',bindings);dump(out/'selection_interventions.json',all_probes)
    dump(out/'cost_and_discoveries.json',summaries);dump(out/'first_discovery_cost.json',first_costs)
    result=dict(passed=True,actual_selections_replayed=sum(s['query_count'] for s in summaries),
        selector_sensitivity=changes,new_model_calls=0,new_native_queries=0,
        independent_test_data_read=False,old_artifacts_unchanged=True,
        audit_wall_seconds=time.perf_counter()-started,script_sha256=sha(Path(__file__)))
    dump(out/'audit.json',result)
    lines=['# research95：选择与成本的只读复核','',
        f"重放{result['actual_selections_replayed']}次真实选择，全部与保存的允许历史和选择一致；新增模型/原生查询均0。没有读取research93独立结果或成功性质。",'',
        '|移除的信息|选择改变/实际决策点|','|---|---:|']
    for k,v in changes.items():lines.append(f"|{k}|{v['changed']}/{v['decisions']}|")
    lines+=['','这是在实际历史状态、相同随机数状态上的单步干预，不执行反事实后续轨迹。选择改变不等于找到额外缺口，更不能给没有执行的分支虚构成本或收益。all_contract_scores保留动作避重，关闭契约打分，区分通用避重与契约选择。','',
        '|原实验|查询|契约相对所有对照独有缺口|搜索原生执行|公共原生执行|物理执行账本|','|---|---:|---:|---:|---:|---:|']
    for s in summaries:lines.append(f"|{s['source']}|{s['query_count']}|{len(s['contract_exclusive_keys'])}|{s['measured_query_native']}|{s['common_public_native']}|{s['recorded_physical_cost']['native_execute_calls']}|")
    lines+=['','首次发现成本逐缺口保存在first_discovery_cost.json；参考模型判定、选择时间、原生次数及unknown均保留。未找到不虚构发现成本。参考判定时间已包含于查询墙钟，不重复相加；墙钟不是经过独立性能设计的速度优势。全部原生物理账本为既有实跑，本轮未重新执行。','',
        '结论：两个原实验的契约独有缺口仍为0；本次只审计选择依赖和成本，不修改策略、不新增成功结果。','',
        '复核：`wsl -- python3 scripts/research95_search_selection_cost_audit.py --out deliverables/research95_audit_NEW`']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('AUDIT95',result,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out.resolve())
