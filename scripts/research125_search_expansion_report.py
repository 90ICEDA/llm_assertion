"""Read-only selector replay, pooled deduplication and actual cost accounting."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import research124_search_expansion as run

ROOT, read, dump, sha = run.ROOT, run.read, run.dump, run.sha


def report(root, audit, out):
    run.b.verify(root)
    state=read(root/'outcome.json'); assert state['status']=='completed'
    native=read(audit/'audit.json');assert native['passed'] and native['source_seal']==sha(root/'sealed.json')
    audit_calls=Counter()
    for taskname in state['tasks']:
        value=read(audit/taskname/'audit.json')
        for kind in ('transaction_reference_calls','sampling_reference_calls','paired_judge_calls'):
            audit_calls[kind]+=value[kind]
    known=set(read(root/'known_development.json')['keys'])
    known_mechanisms=set(read(root/'known_development.json')['mechanisms'])
    checks=[]
    def check(name,value):
        assert value,name;checks.append(name)
    qualification=[];groups=[];discoveries=[];examples={};exposure=[];unknown=[];ref_costs=Counter()
    method_data={m:dict(keys=set(),previously_unregistered=set(),queries=0,repeats=0,critical_unknown=0,later_unknown=0,
        native_executes=0,native_wall_seconds=0.,query_wall_seconds=0.,selector_seconds=0.,reference_calls=0,reference_seconds=0.) for m in run.METHODS}
    execute_count=public_count=0;execute_seconds=0.;public_unknown=Counter()
    for taskname in state['tasks']:
        task=root/taskname;qual=read(task/'qualification.json');qualification.append(qual)
        run.b.verify(task)
        pub=read(task/'public_feedback.json');pair=next(iter(pub));pub=pub[pair]
        records=read(task/'records.json');refs=read(task/'reference_costs.json');costs=read(task/'execute_costs.json')
        check(taskname+'/public_hash',sha(task/'public_feedback.json')==read(task/'public_freeze.json')['sha256'])
        check(taskname+'/bounded_queries',len(records)==(36 if qual['qualified'] else 0))
        check(taskname+'/cost_completeness',len(costs)==20*(len(records)+len(pub['results'])))
        execute_count+=len(costs);execute_seconds+=sum(c['record']['wall_seconds'] for c in costs)
        public_count+=20*len(pub['results'])
        for c in costs:check(c['path']+'/native_status',c['record']['status']=='completed' and c['record']['exit_code']==0)
        for r in pub['results']:
            public_unknown['critical']+=r['unknown'];public_unknown['later']+=r['later_attribution_unknown']
        for r in refs:
            ref_costs['calls:'+r['kind']]+=1;ref_costs['seconds:'+r['kind']]+=r['wall_seconds']
        for r in pub['results']+records:
            folder=(task/'public'/pair/f'q{r["query"]}') if r['stage']=='public' else (task/'queries'/pair/f's{r["seed"]}'/r['method']/f'q{r["query"]}')
            expose=read(folder/'exposure.json')
            exposure.append(dict(task=taskname,stage=r['stage'],seed=r['seed'],method=r['method'],query=r['query'],modes=expose))
            if r['unknown'] or r['later_attribution_unknown']:
                unknown.append(dict(task=taskname,stage=r['stage'],seed=r['seed'],method=r['method'],query=r['query'],
                    critical=r['unknown'],later=r['later_attribution_unknown'],source=(folder/'result.json').relative_to(ROOT).as_posix()))
        for seed in run.SEEDS:
            for method in run.METHODS:
                rr=[r for r in records if r['seed']==seed and r['method']==method]
                if not qual['qualified']:continue
                check(taskname+str(seed)+method+'/equal_budget',len(rr)==run.BUDGET)
                p=run.policy.factory(method,seed);history=[];seen=set(pub['gap_keys']);first={};actions=set();repeats=0
                for r in pub['results']:
                    history.append(run.policy.update(p,method,r['family'],r));actions.add((r['family'],r['duration']))
                for q,r in enumerate(rr):
                    folder=task/'queries'/pair/f's{seed}'/method/f'q{q}'
                    saved=read(folder/'selection.json')
                    choice=run.policy.decision(p,method,seed,q,history)
                    check(str(folder)+'/selector_and_information',choice==saved['chosen'] and history==saved['permitted_history'])
                    check(str(folder)+'/chosen_action',(choice['family'],choice.get('duration'))==(r['family'],r['duration']))
                    check(str(folder)+'/seed',r['stimulus_seed']==seed*100+q)
                    check(str(folder)+'/public_dedup',r['first_new_keys']==sorted(set(r['gap_keys'])-seen)
                          and r['public_unexposed_keys']==sorted(set(r['gap_keys'])-set(pub['gap_keys'])))
                    check(str(folder)+'/history_dedup',r['previously_unregistered_keys']==sorted(set(r['gap_keys'])-known))
                    for key in r['first_new_keys']:
                        first[key]=q+1
                        row=dict(task=taskname,config=dict(depth=qual['depth'],pipeline=qual['pipeline']),candidate=qual['name'],
                            seed=seed,method=method,key=key,first_query=q+1,
                            known_development=key in known,mechanism_known='/'.join(key.split('/')[1:]) in known_mechanisms,
                            source=(folder/'result.json').relative_to(ROOT).as_posix())
                        prefix=str(folder.parent.relative_to(ROOT))+'/'
                        consumed=[c for c in costs if c['path'].startswith(prefix) and int(c['path'][len(prefix):].split('/')[0][1:])<=q]
                        rc=[c for c in refs if c.get('stage')=='search' and c['seed']==seed and c['method']==method and c['query']<=q]
                        row.update(native_executes=len(consumed),native_wall_seconds=sum(c['record']['wall_seconds'] for c in consumed),
                            reference_calls=len(rc),reference_seconds=sum(c['wall_seconds'] for c in rc),
                            query_wall_seconds=sum(v['query_wall_seconds'] for v in rr[:q+1]))
                        check(str(folder)+'/first_cost',len(consumed)==20*(q+1))
                        discoveries.append(row)
                        if key not in examples:
                            examples[key]=dict(discovery=row,witness=next(g for g in r['gaps'] if g['key']==key),
                                candidate=read(task/'candidates'/(qual['name']+'.json')))
                    seen.update(r['gap_keys']);action=(r['family'],r['duration']);repeats+=action in actions;actions.add(action)
                    history.append(run.policy.update(p,method,r['family'],r))
                prefix=(task/'queries'/pair/f's{seed}'/method).relative_to(ROOT).as_posix()+'/'
                cc=[c for c in costs if c['path'].startswith(prefix)]
                rc=[c for c in refs if c.get('stage')=='search' and c['seed']==seed and c['method']==method]
                check(prefix+'/execute_count',len(cc)==20*run.BUDGET)
                group=dict(task=taskname,seed=seed,method=method,first=first,queries=len(rr),repeats=repeats,
                    native_executes=len(cc),native_wall_seconds=sum(c['record']['wall_seconds'] for c in cc),
                    query_wall_seconds=sum(r['query_wall_seconds'] for r in rr),selector_seconds=sum(r['selector_seconds'] for r in rr),
                    reference_calls=len(rc),reference_seconds=sum(c['wall_seconds'] for c in rc),
                    critical_unknown=sum(r['unknown'] for r in rr),later_unknown=sum(r['later_attribution_unknown'] for r in rr))
                groups.append(group);total=method_data[method]
                total['keys'].update(first);total['previously_unregistered'].update(set(first)-known)
                for field in group:
                    if field in total and field not in ('keys','previously_unregistered'):total[field]+=group[field]
    contrasts=[]
    for c in groups:
        if c['method']!='contract_novelty':continue
        for other in groups:
            if (other['task'],other['seed'])!=(c['task'],c['seed']) or other['method']==c['method']:continue
            common=set(c['first'])&set(other['first'])
            contrasts.append(dict(task=c['task'],seed=c['seed'],comparator=other['method'],
                earlier=sum(c['first'][k]<other['first'][k] for k in common),tied=sum(c['first'][k]==other['first'][k] for k in common),
                later=sum(c['first'][k]>other['first'][k] for k in common),
                contract_only=sorted(set(c['first'])-set(other['first'])),other_only=sorted(set(other['first'])-set(c['first']))))
    extra=sorted(method_data['contract_novelty']['keys']-set().union(*(v['keys'] for k,v in method_data.items() if k!='contract_novelty')))
    for method,v in method_data.items():
        v['keys']=sorted(v['keys']);v['previously_unregistered']=sorted(v['previously_unregistered'])
        v['mechanism_keys']=sorted({'/'.join(k.split('/')[1:]) for k in v['keys']})
        v['successful_task_seeds']=sum(bool(g['first']) for g in groups if g['method']==method)
        v['task_seeds']=sum(g['method']==method for g in groups)
    extra_mechanisms=sorted(set(method_data['contract_novelty']['mechanism_keys'])-
        set().union(*(set(v['mechanism_keys']) for m,v in method_data.items() if m!='contract_novelty')))
    builds=[]
    for d,p in run.CONFIGS:
        for n in read(root/'protocol.json')['included']+['reference']:
            folder=root/'builds'/f'd{d}_p{p}'/n
            compiled=read(folder/'compiled.json')
            check(str(folder)+'/parameter_binding',compiled['feedback_config']['depth']==d and compiled['feedback_config']['pipeline']==p)
            builds.append(dict(config=[d,p],name=n,compile=read(folder/'compile.json'),smoke=read(folder/'execute.json') if (folder/'execute.json').exists() else None,
                               tool=read(folder/'tool_version.json')))
    exposure_totals=defaultdict(Counter)
    for row in exposure:
        for mode,values in row['modes'].items():
            counter=exposure_totals[(row['task'],row['stage'],mode)]
            counter['query_observations']+=1
            for field in ('first_violation_rows','detections','misses','critical_unknown','later_unknown'):
                counter[field]+=values[field]
            for ob,count in values['obligations'].items():counter['obligation:'+ob]+=count
    exposure_summary=[dict(task=task,stage=stage,mode=mode,**dict(counts),
        target_exposed=bool(counts['first_violation_rows'])) for (task,stage,mode),counts in sorted(exposure_totals.items())]
    cost=dict(model_calls=0,model_tokens=0,formal_calls=0,compile_calls=len(builds),
        compile_wall_seconds=sum(v['compile']['wall_seconds'] for v in builds),
        compile_smoke_calls=sum(v['smoke'] is not None for v in builds),
        smoke_wall_seconds=sum(v['smoke']['wall_seconds'] for v in builds if v['smoke']),
        public_native_executes=public_count,search_native_executes=execute_count-public_count,
        total_query_executes=execute_count,total_query_native_wall_seconds=execute_seconds,
        total_physical_executes=execute_count+sum(v['smoke'] is not None for v in builds),
        reference=dict(ref_costs),audit_reference_calls=dict(audit_calls),audit_reference_wall_seconds=native['reference_wall_seconds'],
        experiment_elapsed_seconds=state['elapsed_seconds'],timing_scope='Four concurrent workers; wall times descriptive. Reference time is nested in query time, never added twice. Shared build/public cost separate.')
    check('audit_execute_count',native['native_replays_verified']==execute_count)
    check('all_16_parameter_tasks',len(qualification)==16)
    check('all_search_queries',sum(v['queries'] for v in method_data.values())==state['search_queries'])
    union=set().union(*(set(v['keys']) for v in method_data.values()))
    result=dict(passed=True,checks=len(checks),qualified_tasks=sum(q['qualified'] for q in qualification),parameter_tasks=16,
        original_candidates=9,prior_eligible_candidates=8,methods=method_data,contract_exclusive_keys=extra,
        contract_exclusive_mechanisms=extra_mechanisms,
        public_unexposed_union=sorted(union),previously_unregistered_union=sorted(union-known),
        previously_unregistered_mechanisms=sorted({'/'.join(k.split('/')[1:]) for k in union}-known_mechanisms),
        novelty_limit='Unregistered in partial development registry is not globally new Bug. All faults artificial and already implemented.',
        public_unknown=dict(public_unknown),new_accepted_versions=0,new_independent_tests=0,model_calls=0,
        scope='Search selection transfer only, not native SVA generation/refinement or independent assertion acceptance.')
    out.mkdir(parents=True,exist_ok=False)
    for name,value in [('result',result),('qualification',qualification),('groups',groups),('contrasts',contrasts),('first_discovery_cost',discoveries),
                       ('exposure',exposure),('exposure_summary',exposure_summary),('unknown',unknown),('examples',list(examples.values())),('cost',cost),('builds',builds),('checks',checks)]:dump(out/(name+'.json'),value)
    lines=['# research124 搜索扩展实际结果','',f'16个候选×参数任务中{result["qualified_tasks"]}个通过资格。执行{state["search_queries"]}次搜索查询；两个固定种子、六策略、每轨迹3查询。模型调用0。',
        '', '|策略|发现公共之外缺口的任务×种子|去重候选缺口|去候选机制类|历史登记之外|重复动作|查询|原生执行|关键unknown|后续归因unknown|', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for m,v in method_data.items():lines.append(f'|{m}|{v["successful_task_seeds"]}/{v["task_seeds"]}|{len(v["keys"])}|{len(v["mechanism_keys"])}|{len(v["previously_unregistered"])}|{v["repeats"]}|{v["queries"]}|{v["native_executes"]}|{v["critical_unknown"]}|{v["later_unknown"]}|')
    lines+=['',f'契约相对所有对照并集独有候选缺口：{len(extra)}，去除候选身份后的独有机制类：{len(extra_mechanisms)}。公共之外并集{len(union)}；部分历史登记之外{len(union-known)}；登记之外失效机制{len(result["previously_unregistered_mechanisms"])}。不按参数、种子、周期、长短波形重复计缺口；候选缺口不是独立Bug。',
        '', '|对照|共同缺口契约更早/相同/更晚|契约独有任务×种子缺口|对照独有|', '|---|---:|---:|---:|']
    for m in run.METHODS:
        if m=='contract_novelty':continue
        rr=[r for r in contrasts if r['comparator']==m]
        lines.append(f'|{m}|{sum(r["earlier"] for r in rr)}/{sum(r["tied"] for r in rr)}/{sum(r["later"] for r in rr)}|{sum(len(r["contract_only"]) for r in rr)}|{sum(len(r["other_only"]) for r in rr)}|')
    lines+=['','三查询未发现按预算删失，不能虚构首次发现时间。公共之外但历史已知的复现不称历史新发现。',
        '', '|深度/流水|候选|资格|曝光首违例观察数|排除原因|', '|---|---|---|---:|---|']
    for q in qualification:lines.append(f'|{q["depth"]}/{q["pipeline"]}|{q["name"]}|{q["qualified"]}|{q["first_violation_observations"]}|{q["reasons"]}|')
    lines+=['', 'c07因原公共资格失败未进入参数执行；保留在原始9候选分母。未曝光义务不算通过，详见exposure_summary.json及逐查询exposure.json；unknown保留在unknown.json。',
        '', f'成本：编译{cost["compile_calls"]}，冒烟{cost["compile_smoke_calls"]}，公共执行{public_count}，搜索执行{execute_count-public_count}。审计复核{native["native_replays_verified"]}份原生日志；参考成本、实际首次发现成本及命令见cost.json、first_discovery_cost.json、builds.json。',
        '', '参数为Depth2/pipeline1、Depth4/pipeline2。实际FIFO RTL加人工故障；有限仿真，不是上游新Bug或形式化证明。无新模型接受、无新独立验收、防退化恢复未在本实验中测量。没有读取research113/116独立测试。']
    lines+=['','复核与重现实验（已有目录不能覆盖；重跑须选择新目录，不改封存输入）：','```powershell',
        'wsl -- python3 scripts/research124_search_expansion.py prepare --out deliverables/research124_NEW',
        'wsl -- python3 scripts/research124_search_expansion.py run --out deliverables/research124_NEW',
        f'wsl -- python3 scripts/research124_search_expansion.py audit --out {root.relative_to(ROOT).as_posix()} --audit-out deliverables/research124_audit_NEW',
        f'wsl -- python3 scripts/research125_search_expansion_report.py --run {root.relative_to(ROOT).as_posix()} --audit {audit.relative_to(ROOT).as_posix()} --out deliverables/research125_report_NEW',
        '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    traces=['# 实际额外曝光的搜索案例','', '断言未修改；以下为开发搜索证据，不是新生成或独立验收。','']
    selected=sorted(examples.values(),key=lambda e:(e['discovery']['method']!='contract_novelty',e['discovery']['key']))[:2]
    for e in selected:
        d=e['discovery'];w=e['witness']
        traces += ['## '+d['key'],'',json.dumps(d,ensure_ascii=False,indent=2),'','```systemverilog']
        traces += [a['property'] for a in e['candidate']['assertions'] if w['obligation'] in a['obligations']]
        traces += ['```','触发分类：'+str(w.get('trigger_class')),'验证条件：'+str(w.get('validation',{}).get('conditions')),
                   '原始回放：'+w['replay_source'],'']
    (out/'CASE_TRACE.md').write_text('\n'.join(traces)+'\n',encoding='utf-8')
    task_bindings={}
    for taskname in state['tasks']:
        for filename in ('records.json','reference_costs.json','execute_costs.json','qualification.json','public_feedback.json','outcome.json'):
            path=root/taskname/filename;task_bindings[path.relative_to(ROOT).as_posix()]=sha(path)
        path=audit/taskname/'audit.json';task_bindings[path.relative_to(ROOT).as_posix()]=sha(path)
    dump(out/'bindings.json',dict(source_seal=sha(root/'sealed.json'),outcome=sha(root/'outcome.json'),native_audit=sha(audit/'audit.json'),
        report_script=sha(Path(__file__)),task_inputs=task_bindings))
    print('REPORT125',dict(qualified=result['qualified_tasks'],queries=state['search_queries'],public_unexposed=len(union),
        unregistered=len(union-known),contract_exclusive=len(extra),native=execute_count,checks=len(checks)),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True);ap.add_argument('--audit',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();report(a.run.resolve(),a.audit.resolve(),a.out.resolve())
