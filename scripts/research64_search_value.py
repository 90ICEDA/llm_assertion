"""Native development comparison: public novelty, adaptive selection, full costs.

No LLM requests or independent-test reads. Existing experiments remain immutable.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import time
from unittest.mock import patch

import research42_search as prior
import research15_search_experiment as grammar
import research15_evidence as evidence
from research17_report import cost_audit

loop, extension = prior.loop, prior.extension
ROOT=loop.ROOT
read,dump=loop.read,loop.dump
SEEDS=(6401,6413)
METHODS=('ordinary','candidate_disagreement','raw_difference','contract_coverage','coverage_sweep')
MODES=('correct','stall_glitch','valid_withdraw_stalled','valid_withdraw_release',
       'long_valid_withdraw_stalled','long_valid_withdraw_release','reset_residue','drop')
SOURCES=dict(pre_valid=ROOT/'deliverables/research20_closed_loop_20261018_r06/core/frozen_candidate.json',
             bounded=prior.SOURCES['initial'],valid=prior.SOURCES['repaired'])
PAIRS=(('pre_valid','valid'),('bounded','valid'),('valid','pre_valid'))
BUDGET=4


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def mechanism(mode):
    # Duration threshold variants are NOT separate failure mechanisms.
    return mode.removeprefix('long_')


def key(candidate,kind,ob,mode):
    return '/'.join((loop.sha(candidate),kind,ob,mechanism(mode)))


def schedule(seed,family,duration=None):
    if family=='backpressure':return prior.stimulus(seed,duration)
    return grammar.stimulus(seed,family)


def historical_registry():
    files=[ROOT/'deliverables/research42_search_20261022_r01/results.json',
           ROOT/'deliverables/research42_search_sweep_20261022_r01/results.json',
           ROOT/'deliverables/research30_search_compare_20261020_r01/results.json']
    keys=set();mechanisms=set();sources=[]
    for path in files:
        if not path.exists():continue
        values=read(path);found=set()
        def walk(value):
            if isinstance(value,dict):
                k=value.get('key')
                if isinstance(k,str) and len(k.split('/'))==4:
                    h,kind,ob,m=k.split('/');normalized='/'.join((h,kind,ob,mechanism(m)))
                    found.add(normalized);mechanisms.add('/'.join((kind,ob,mechanism(m))))
                for v in value.values():walk(v)
            elif isinstance(value,list):
                for v in value:walk(v)
        walk(values);keys.update(found)
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=digest(path),keys=sorted(found)))
    return dict(sources=sources,keys=sorted(keys),mechanisms=sorted(mechanisms),
        completeness='Partial evidence registry, not exhaustive across all prior campaigns. Absent entries are historical novelty UNKNOWN, never globally new.',
        known_fault_families='All fault implementations are previously developed artificial mutations, not newly discovered upstream defects.')


def decision(policy,method,seed,q,history):
    if method=='coverage_sweep':
        family,duration=(('backpressure',1),('backpressure',16),('reset_pending',None),('tail_loss',None))[q]
        return dict(family=family,duration=duration,target_obligation=None,reason='fixed preregistered sweep; no feedback',deficit_scores={})
    chosen=policy.choose()
    duration=None
    if chosen['family']=='backpressure':
        if method=='contract_coverage':
            maximum=max((h.get('maximum_stall',0) for h in history),default=0)
            duration=next((n for n in (1,4,16) if n>maximum),16)
        else:duration=random.Random(seed*1000+q).choice((1,4,16))
    return dict(chosen,duration=duration)


def update(policy,method,family,result):
    if method=='coverage_sweep':return dict(family=family)
    value=policy.update(family,result)
    if method=='contract_coverage':value['maximum_stall']=result['maximum_stall']
    return value


@contextmanager
def metered(calls,context):
    original=extension.runtime.oracle
    sampling=loop.runtime.qualify_sampling
    def timed(label,fn):
        def call(*args,**kwargs):
            start=time.perf_counter()
            try:return fn(*args,**kwargs)
            finally:calls.append(dict(**context,kind=label,wall_seconds=time.perf_counter()-start))
        return call
    with patch.object(extension.runtime,'oracle',timed('transaction_reference',original)),patch.object(loop.runtime,'qualify_sampling',timed('sampling_reference',sampling)):
        yield


def query(out,builds,candidates,names,rows,context,calls):
    runs={};begin=time.perf_counter()
    for n in names:
        runs[n]={}
        for mode in MODES:
            with metered(calls,dict(context,candidate=n,mode=mode)):
                runs[n][mode]=loop.runtime.execute(builds[n],out/n/mode,rows,mode)
    initial,second=names
    fixed=runs[initial]['correct']
    healthy=all(r['native']['execution_status']=='completed' and r['native']['tool_support_status']=='supported_for_compiled_constructs'
                and r['sampling_qualification']['status']=='passed' and r['oracle']['legality']=='legal' and not r['oracle']['unknown']
                for rr in runs.values() for r in rr.values())
    correct_reference=all(not runs[n]['correct']['oracle']['violations'] for n in names)
    correct_accepts={n:not runs[n]['correct']['native']['failures'] for n in names}
    gaps=[];unknown=0;later=0;protected=Counter();checks=Counter();effective=Counter();validations=[]
    for mode in MODES[1:]:
        start=time.perf_counter()
        group=evidence.paired_ledger(fixed,runs[initial][mode],str(out.relative_to(ROOT))+':'+mode)
        info=loop.inspect(group['ledger'])
        calls.append(dict(**context,kind='paired_obligation_judge',candidate=initial,mode=mode,wall_seconds=time.perf_counter()-start))
        unknown+=len(info['unknown']);later+=len(group['exclusions'])
        # Keep replay paths, individual witnesses and attribution exclusions, not copied megabytes of legal projections.
        dump(out/'judgements'/f'{mode}.json',dict(stats=group['stats'],exclusions=group['exclusions'],
            unknown_rows=[info['rows'][k] for k in sorted(info['unknown'])],
            target_rows=[r for r in group['ledger'] if r['oracle'].get('first_violation_in_epoch')],
            ledger_replay='research15_evidence.paired_ledger on saved correct/mutant replay.json'))
        for k in info['detections']:protected[info['rows'][k]['obligation']]+=1
        for k in sorted(info['misses']):
            row=info['rows'][k];validation=prior.validate_gap(row,fixed,runs[initial][mode])
            valid=healthy and correct_reference and correct_accepts[initial] and validation['valid']
            validations.append(dict(evidence_id=k,valid=valid,conditions=validation['conditions']))
            if valid:
                gaps.append(dict(key=key(candidates[initial],'FN',row['obligation'],mode),kind='FN',
                    obligation=row['obligation'],mechanism=mechanism(mode),mode=mode,
                    evidence=row,trigger_class=validation['trigger_class'],validation=validation,
                    replay_source=str(out/initial/mode)))
    # False positives are independently confirmed on the correct, legal reference.
    if healthy and correct_reference:
        fault_class='legal_reset' if context['family']=='reset_pending' else 'legal_stall' if context['family']=='backpressure' else 'legal_transaction'
        for a in candidates[initial]['assertions']:
            events=evidence.marker_map(fixed['native'],'failures').get(a['id'],set())
            for ob in a['obligations']:
                if events:gaps.append(dict(key=key(candidates[initial],'FP',ob,fault_class),kind='FP',obligation=ob,
                    mechanism=fault_class,mode='correct',cycles=sorted(events),assertion_id=a['id'],replay_source=str(out/initial/'correct')))
    for check in fixed['oracle']['checks']:checks[check['obligation']]+=1
    markers=evidence.marker_map(fixed['native'],'triggers')
    for a in fixed['candidate']['assertions']:
        for cycle in markers.get(a['id'],set()):
            for ob in a['obligations']:
                if any(c['obligation']==ob and c['cycle']==cycle+a['derived_delay'] for c in fixed['oracle']['checks']):effective[ob]+=1
    xor=sum(len(prior.failures(runs[initial][m]) ^ prior.failures(runs[second][m])) for m in MODES)
    diff=sum(any(a[k]!=b[k] for k in ('mvalid','mdata')) for m in MODES[1:]
             for a,b in zip(fixed['trace'],runs[initial][m]['trace']))
    keys=sorted({g['key'] for g in gaps})
    result=dict(**context,healthy=healthy and correct_reference,correct_accepts=correct_accepts,
        gaps=gaps,gap_keys=keys,validations=validations,unknown=unknown,later_attribution_unknown=later,
        status='ok' if healthy and correct_reference else 'unknown',
        fixed_obligation_checks=dict(checks),effective_native_triggers=dict(effective),causal_protected=dict(protected),
        obligation_gap_keys=[g['mechanism']+'/'+g['obligation'] for g in gaps],
        candidate_disagreement_count=xor,raw_difference_count=diff,maximum_stall=prior.stall_length(fixed['trace']),
        native_executions=len(names)*len(MODES),query_wall_seconds=time.perf_counter()-begin)
    dump(out/'result.json',result)
    return result


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    candidates={n:read(p) for n,p in SOURCES.items()}
    for n,c in candidates.items():
        assert c['assertions'];dump(out/'candidates'/f'{n}.json',c)
        if (SOURCES[n].parent/'freeze.json').exists():
            assert loop.sha(c)==read(SOURCES[n].parent/'freeze.json')['candidate_sha256']
    assert len({loop.sha(c) for c in candidates.values()})==3
    dump(out/'candidate_sources.json',{n:dict(path=str(SOURCES[n]),sha256=digest(SOURCES[n]),content_hash=loop.sha(c)) for n,c in candidates.items()})
    shutil.copy2(extension.runtime.RTL,out/'axis_fifo.v')
    dump(out/'historical_registry.json',historical_registry())
    dump(out/'protocol.json',dict(seeds=SEEDS,methods=METHODS,pairs=PAIRS,budget=BUDGET,depth=4,pipeline=1,modes=MODES,
        common_feedback='Two mandatory public schedules: overlap and duration1 backpressure; all eight modes, both candidates. Public gap registry is frozen before any search. Candidate admission requires native compile, valid reference, zero correct-control false alarms on both schedules. No requirement to already detect all target faults.',
        information='All arms receive the same public candidates, RTL, specification, stimulus grammar, mode names and public feedback. Search observations differ by method: ordinary family only; disagreement WHOLE candidate XOR; differential output mismatch; contract own checks/triggers/protected/gaps/max-stall. Offline judge never leaks to other choosers.',
        policy='Reuse research15 Policy deficit scoring/attempt discount for contract; three duration buckets chosen from own measured stall coverage. Four fixed sweep actions provide no-feedback control. No policies read future outcomes.',
        novelty='Per pair: subtract complete public-feedback gap-key set, then subtract own previously found keys. Cross-method incremental set differences computed only afterward. Audited historical matches reported separately; absence from partial history remains unknown.',
        dedup='candidate hash / FN or FP / obligation / failure mechanism. Collapse long/short valid-withdrawal threshold variants. Cycles, seeds, data, and query families do not create new gaps. Report mechanism keys without candidate hash separately.',
        qualification='Three preregistered candidate pairs; failed pair retained in denominator, not silently replaced. Two seeds, one FIFO depth/configuration. Not the legacy 11 procedural candidate pairs.',
        accounting='16 fresh native executions/query, no cache. Shared compilation and public setup charged physically once and allocated logically per pair. Instrument actual transaction oracle, sampling oracle, paired judge, selector CPU and native time. Comparator oracle is measurement. Contract primary oracle also supports selection; other arms oracle is evaluation-only. End-to-end cost includes both; not an optimized baseline deployment cost.',
        scope='Exploratory development comparison on previously known artificial FIFO faults, not independent testing, new historical defects, or a claim of positive gain. No model calls/tokens/formal calls. No research63 independent inputs read.',
        origin_version='No usable Git repository; source/input hashes retained.',prepared_at=time.time()))
    dump(out/'code_versions.json',{str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file()})
    dump(out/'outcome.json',dict(status='prepared'))


def verify(out):
    for p,h in read(out/'sealed.json').items():assert digest(out/p)==h,p
    for p,h in read(out/'code_versions.json').items():assert digest(ROOT/p)==h,p


def run(out):
    verify(out);assert read(out/'outcome.json')['status']=='prepared'
    candidates={n:read(out/'candidates'/f'{n}.json') for n in SOURCES}
    calls=[];records=[];public={};admission=[];start=time.perf_counter()
    dump(out/'outcome.json',dict(status='running'))
    try:
        with extension.installed():
            builds={n:loop.runtime.build(c,out/'compiled'/n,4,1) for n,c in candidates.items()}
            assert all(b['native']['compile_status']=='passed' for b in builds.values())
            # Complete public evidence for every pair BEFORE search. Cost sharing is explicit.
            for first,second in PAIRS:
                pair=first+'__'+second;pub=[]
                for i,(family,duration) in enumerate((('overlap',None),('backpressure',1))):
                    result=query(out/'public'/pair/f'q{i}',builds,candidates,(first,second),schedule(64000+i,family,duration),
                        dict(pair=pair,stage='public',method='common',seed=0,query=i,family=family,duration=duration),calls)
                    pub.append(result)
                okay=all(r['healthy'] and all(r['correct_accepts'].values()) for r in pub)
                public[pair]=dict(results=pub,gap_keys=sorted({k for r in pub for k in r['gap_keys']}))
                admission.append(dict(pair=pair,qualified=okay,reason='native and reference pass; both correct controls accepted' if okay else 'public native/reference/control failure',primary_hash=loop.sha(candidates[first])))
            dump(out/'public_feedback.json',public);dump(out/'qualification.json',admission)
            dump(out/'public_freeze.json',dict(sha256=digest(out/'public_feedback.json'),at=time.time()))
            for pairinfo in admission:
                if not pairinfo['qualified']:continue
                pair=pairinfo['pair'];first,second=pair.split('__')
                for seed in SEEDS:
                    for method in METHODS:
                        policy=grammar.Policy(method if method!='coverage_sweep' else 'ordinary',seed)
                        history=[];seen=set(public[pair]['gap_keys'])
                        for r in public[pair]['results']:history.append(update(policy,method,r['family'],r))
                        for q in range(BUDGET):
                            folder=out/'queries'/pair/f's{seed}'/method/f'q{q}'
                            before_choice=copy.deepcopy(policy)
                            t=time.perf_counter();chosen=decision(policy,method,seed,q,history);selector_time=time.perf_counter()-t
                            probes=[]
                            if method=='contract_coverage':
                                # Sensitivity diagnostics only. No synthetic input is executed or scored as discovery.
                                for ob in grammar.OBLIGATIONS:
                                    altered=copy.deepcopy(before_choice);altered.checks[ob]=0;altered.triggers[ob]=0;altered.protected[ob]=0
                                    probes.append(dict(obligation=ob,decision=decision(altered,method,seed,q,history)))
                            dump(folder/'selection.json',dict(chosen=chosen,permitted_history=history,selector_seconds=selector_time,counterfactuals=probes))
                            r=query(folder,builds,candidates,(first,second),schedule(seed*100+q,chosen['family'],chosen['duration']),
                                dict(pair=pair,stage='search',method=method,seed=seed,query=q,family=chosen['family'],duration=chosen['duration']),calls)
                            r['public_unexposed_keys']=sorted(set(r['gap_keys'])-set(public[pair]['gap_keys']))
                            r['first_new_keys']=sorted(set(r['gap_keys'])-seen)
                            r['repeated_observations']=len(r['gaps'])-len(r['first_new_keys'])
                            r['selector_seconds']=selector_time
                            seen.update(r['gap_keys']);history.append(update(policy,method,r['family'],r))
                            dump(folder/'result.json',r);records.append(r)
                            dump(out/'records.json',records);dump(out/'reference_costs.json',calls)
                            print(pair,seed,method,q,chosen['family'],chosen['duration'],'new',len(r['first_new_keys']),flush=True)
        verify(out)
        dump(out/'outcome.json',dict(status='completed',pairs_planned=len(PAIRS),pairs_qualified=sum(a['qualified'] for a in admission),
            queries=len(records),elapsed_seconds=time.perf_counter()-start,model_calls=0,formal_calls=0))
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='failed',error=repr(exc),queries=len(records)))
        raise
    finally:
        dump(out/'reference_costs.json',calls)
    report(out)


def native_cost(out):
    files=[]
    for parent,dirs,names in os.walk(out):
        dirs[:]=[d for d in dirs if d not in ('obj_dir','__pycache__')]
        files.extend(Path(parent)/n for n in names if n in ('compile.json','execute.json','tool_version.json','result.json','attempt.json'))
    return cost_audit(out,files)


def report(out):
    verify(out)
    records=read(out/'records.json');public=read(out/'public_feedback.json');historical=read(out/'historical_registry.json')
    assert digest(out/'public_feedback.json')==read(out/'public_freeze.json')['sha256']
    calls=read(out/'reference_costs.json');summary=[];audits=[];examples=[]
    for pairinfo in read(out/'qualification.json'):
        pair=pairinfo['pair']
        if not pairinfo['qualified']:continue
        for seed in SEEDS:
            sets={m:{k for r in records if r['pair']==pair and r['seed']==seed and r['method']==m for k in r['public_unexposed_keys']} for m in METHODS}
            for method in METHODS:
                rr=[r for r in records if r['pair']==pair and r['seed']==seed and r['method']==method]
                assert len(rr)==BUDGET
                policy=grammar.Policy(method if method!='coverage_sweep' else 'ordinary',seed);history=[];seen=set(public[pair]['gap_keys'])
                first={};changed=0;non_sweep=0
                for r in public[pair]['results']:history.append(update(policy,method,r['family'],r))
                for q,r in enumerate(rr):
                    folder=out/'queries'/pair/f's{seed}'/method/f'q{q}';selection=read(folder/'selection.json')
                    chosen=decision(policy,method,seed,q,history)
                    assert chosen==selection['chosen'] and history==selection['permitted_history']
                    assert r['first_new_keys']==sorted(set(r['gap_keys'])-seen)
                    assert r['public_unexposed_keys']==sorted(set(r['gap_keys'])-set(public[pair]['gap_keys']))
                    seen.update(r['gap_keys'])
                    for k in r['first_new_keys']:first[k]=q+1
                    if method=='contract_coverage':
                        changed+=any((p['decision']['family'],p['decision']['duration'])!=(chosen['family'],chosen['duration']) for p in selection['counterfactuals'])
                        fixed=decision(None,'coverage_sweep',seed,q,[])
                        non_sweep+=(fixed['family'],fixed['duration'])!=(chosen['family'],chosen['duration'])
                    history.append(update(policy,method,r['family'],r))
                    if r['first_new_keys'] and len(examples)<10:
                        examples.extend([g for g in r['gaps'] if g['key'] in r['first_new_keys']][:1])
                cc=[c for c in calls if c['stage']=='search' and c['pair']==pair and c['seed']==seed and c['method']==method]
                novelty={k:('previously_observed_same_candidate' if k in historical['keys'] else
                    'previously_observed_mechanism_other_candidate' if '/'.join(k.split('/')[1:]) in historical['mechanisms'] else 'unknown_partial_history') for k in sets[method]}
                item=dict(pair=pair,seed=seed,method=method,queries=len(rr),native_executions=sum(r['native_executions'] for r in rr),
                    all_gap_keys=sorted({k for r in rr for k in r['gap_keys']}),public_exposed_keys=public[pair]['gap_keys'],
                    public_unexposed_keys=sorted(sets[method]),first_query=first,historical_novelty=novelty,
                    repeated_observations=sum(r['repeated_observations'] for r in rr),unknown=sum(r['unknown'] for r in rr),
                    later_attribution_unknown=sum(r['later_attribution_unknown'] for r in rr),
                    failed_queries=sum(not r['healthy'] for r in rr),
                    reference_cost={kind:dict(calls=sum(c['kind']==kind for c in cc),wall_seconds=sum(c['wall_seconds'] for c in cc if c['kind']==kind)) for kind in ('transaction_reference','sampling_reference','paired_obligation_judge')},
                    selector_seconds=sum(r['selector_seconds'] for r in rr),query_wall_seconds=sum(r['query_wall_seconds'] for r in rr),
                    contract_extra_vs_method=sorted(sets['contract_coverage']-sets[method]),
                    method_extra_vs_contract=sorted(sets[method]-sets['contract_coverage']),
                    feedback_sensitivity_changed_queries=changed,actual_choices_differ_from_fixed_sweep=non_sweep,
                    selections=[dict(family=r['family'],duration=r['duration']) for r in rr])
                summary.append(item);audits.append(dict(pair=pair,seed=seed,method=method,policy_replay_and_novelty=True))
    cost=native_cost(out);dump(out/'cost.json',cost)
    assert cost['total']['native_execute_calls']==sum(r['native_executions'] for r in records)+len(PAIRS)*2*16+len(SOURCES)
    dump(out/'summary.json',summary);dump(out/'policy_audit.json',audits);dump(out/'examples.json',examples)
    totals={m:sorted({k for x in summary if x['method']==m for k in x['public_unexposed_keys']}) for m in METHODS}
    dump(out/'method_unions.json',dict(candidate_gap_keys=totals,
        mechanism_keys={m:sorted({'/'.join(k.split('/')[1:]) for k in ks}) for m,ks in totals.items()},
        contract_extra_vs_all_baselines=sorted(set(totals['contract_coverage'])-set().union(*(set(totals[m]) for m in METHODS if m!='contract_coverage')))))
    lines=['# research64：公共反馈之外的搜索价值','',
        '本实验为开发性比较：已知人工FIFO故障、历史真实模型候选、Depth4/RAM_PIPELINE1。没有读取独立测试，没有模型调用。旧research42/50无额外收益结果保持不变。', '',
        '公共反馈包含同一overlap与短背压输入下的全部故障执行；先冻结公共缺口，再启动各方法。长短valid撤销变体按同一机制去重。公共反馈新缺口不等于整个研究的新发现；部分历史索引未命中的新颖性保留unknown。', '',
        '|候选对|种子|方法|公共之外缺口|首发现查询|重复观察|后续归因unknown|',
        '|---|---:|---|---:|---|---:|---:|']
    for s in summary:lines.append(f"|{s['pair']}|{s['seed']}|{s['method']}|{len(s['public_unexposed_keys'])}|{','.join(map(str,sorted(s['first_query'].values()))) or '未发现'}|{s['repeated_observations']}|{s['later_attribution_unknown']}|")
    lines+=['','逐缺口身份、历史是否已见、方法间增量、选择轨迹和参考模型成本见summary.json。机制去重并集见method_unions.json；全物理成本见cost.json，参考模型逐次计时见reference_costs.json。',
        '',f"实际原生执行{cost['total']['native_execute_calls']}次、编译{cost['total']['native_compile_calls']}次，模型与形式化0。未将计时诊断的反事实输入当作真实搜索发现。",
        '', '契约策略复用已有义务缺口计分，实际消费自身参考检查、有效触发、目标检出与缺口反馈；记录反馈改变选样的反事实敏感性，但敏感性不是性能收益。固定覆盖臂完全不读反馈。各方法都执行参考模型作为统一事后测量；契约还消费其中一部分作选择，因此要同时报告端到端成本与处理/测量角色。',
        '', '原始RTL仍为axis_fifo；所有故障为显式人工输出边界变异，不是历史修复。3对候选来自同一父案例，不是3个独立Bug，也未冒充旧11对程序检查候选。unknown和不合格候选不能删除。',
        '', '复核：`wsl -- python3 scripts/research64_search_value.py report --out '+str(out.relative_to(ROOT)).replace('\\','/')+'`']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('REPORT',json.dumps({m:len(ks) for m,ks in totals.items()}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','report']);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();globals()[a.action](a.out.resolve())
