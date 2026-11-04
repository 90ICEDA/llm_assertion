"""Final R196 tables and paired analyses, from immutable real execution records."""
import argparse
from collections import Counter
import copy
from html import escape
import json
import os
from pathlib import Path
import statistics
import sys
from research194_refinement_runner import ROOT,read,dump,file_hash
from research194_refinement import digest
from research194_report import trajectories,aggregate,cross_design_table,table
from research196_cost_sections import GROUPS
from research194_active_search import gaps as evidence_gaps


def mean(values):return statistics.mean(values) if values else None
def optional(path,default):return read(path) if Path(path).exists() else default


def classify_round(record):
    status=record.get('status');decision=record.get('decision',{})
    if status=='accepted':return 'accepted_improvement'
    if status=='no_change':return 'unchanged_proposal'
    if status=='interface_rejected':return 'interface_rejected'
    if status=='model_transport_or_decode_failure':return 'model_call_or_decode_failure'
    if status=='infrastructure_interrupted':return 'native_or_acquisition_execution_failure'
    if status=='unknown_acquisition_or_history' or decision.get('critical_unknown'):return 'unknown_evidence_or_execution'
    if decision.get('regression'):return 'confirmed_regression_rejected'
    if decision.get('component_guard',{}).get('blocked_components'):return 'component_inactivity_rejected'
    if status=='rejected' and not (decision.get('gained_ids') or decision.get('transaction_gained_ids') or decision.get('fixed_false_positive_ids')):return 'no_confirmed_improvement'
    return 'other_gate_rejection' if status=='rejected' else status


def reason_names(items):
    names=[]
    for item in items:
        values=item.get('reason',item.get('reasons','unspecified')) if isinstance(item,dict) else item
        if not isinstance(values,list):values=[values]
        names.extend(str(v).split(':',1)[0] for v in values)
    return sorted(set(names))


def request_diagnostics(execution):
    rows=[]
    def size(value):return len(json.dumps(value,separators=(',',':'),ensure_ascii=True).encode())
    for p in sorted(Path(execution).glob('*/*/*/refinement/round*/model_call/request.json')):
        request=read(p);context=json.loads(request['messages'][-1]['content']);result=optional(p.parent/'result.json',{})
        history=context.get('earlier_rounds',[])
        guards=[r.get('decision',{}).get('component_guard',{}) for r in history]
        rows.append(dict(id='/'.join(p.relative_to(execution).parts[:3]),round=p.parent.parent.name,status=result.get('status'),
            request_file_bytes=p.stat().st_size,context_bytes=size(context),history_bytes=size(history),component_audit_bytes=size(guards),
            development_observation_bytes=size(context.get('development_observations',[])),prompt_tokens=result.get('prompt_tokens'),
            assertion_count=len(context.get('current_assertions',[])),observation_count=len(context.get('development_observations',[])),
            null_obligation_observations=sum(e.get('obligation') is None for e in context.get('development_observations',[])),
            largest_observation_bytes=max([size(e) for e in context.get('development_observations',[])] or [0]),
            completion_tokens=result.get('completion_tokens'),http_status=result.get('error',{}).get('http_status')))
    return dict(rows=rows,
        interpretation='Measure serialized field size to identify feedback growth. HTTP status without provider error body cannot establish rejection cause; do not infer a context limit or billable usage.')


def eligible(row):
    return bool(row['valid_reachable_fault'] and row['native_complete'] and row['reference_complete'] and not row['unknown_records'] and row['target_ids'])


def paired(acceptance):
    cells=[];summary=[]
    for group,arms in GROUPS.items():
        for cid in sorted({r['case_id'] for r in acceptance}):
            population=[r for r in acceptance if r['case_id']==cid and r.get('role')!='initial_control']
            for seed in sorted({r['seed'] for r in population}):
                for fault in sorted({r['fault'] for r in population}):
                    rows={a:next(r for r in population if r['seed']==seed and r['fault']==fault and r['search_strategy']+'_'+r['strategy']==arm) for a,arm in arms.items()}
                    reasons=[]
                    if any(not eligible(r) for r in rows.values()):reasons.append('unknown_incomplete_or_unexposed')
                    if len({tuple(sorted(r['target_ids'])) for r in rows.values()})!=1:reasons.append('target_mismatch')
                    cell=dict(group=group,case_id=cid,parent_bug=next(iter(rows.values()))['parent_bug'],seed=seed,fault=fault,eligible=not reasons,reasons=reasons)
                    if not reasons:
                        cell['metrics']={a:dict(transaction_rate=r['transaction_detected']/r['target_transaction_obligations'],timely_rate=r['detected']/r['target_transaction_obligations'],
                            fp_records=r['false_positive_records'],necessary_obligation_rate=r['necessary_obligation_transaction_protection_rate']) for a,r in rows.items()}
                        cell['obligation_sets']={a:dict(necessary=r.get('necessary_obligations',[]),exposed=r.get('exposed_obligations',[]),
                            protected=r.get('fully_transaction_protected_exposed_obligations',[])) for a,r in rows.items()}
                    cells.append(cell)
        parents=[]
        for cid in sorted({c['case_id'] for c in cells if c['group']==group}):
            cc=[c for c in cells if c['group']==group and c['case_id']==cid];seeds=sorted({c['seed'] for c in cc})
            common_faults=set.intersection(*({c['fault'] for c in cc if c['seed']==s and c['eligible']} for s in seeds))
            chosen=[c for c in cc if c['fault'] in common_faults]
            if len(seeds)!=2 or not chosen:continue
            metrics={a:{k:mean([c['metrics'][a][k] for c in chosen]) for k in chosen[0]['metrics'][a]} for a in arms}
            for a in arms:
                rates=[]
                for seed in seeds:
                    obs=[c['obligation_sets'][a] for c in chosen if c['seed']==seed]
                    needed=set().union(*(set(o['necessary']) for o in obs));exposed=set().union(*(set(o['exposed']) for o in obs))
                    failed=set().union(*(set(o['exposed'])-set(o['protected']) for o in obs))
                    if needed:rates.append(len(exposed-failed)/len(needed))
                if rates:metrics[a]['necessary_obligation_rate']=mean(rates)
            parents.append(dict(case_id=cid,eligible_faults=sorted(common_faults),metrics=metrics))
        for arm in arms:
            summary.append(dict(group=group,arm=arm,paired_parents=len(parents),parent_ids=[p['case_id'] for p in parents],
                **{k:mean([p['metrics'][arm][k] for p in parents]) for k in ('transaction_rate','timely_rate','fp_records','necessary_obligation_rate')}))
    ablation={r['arm']:r for r in summary if r['group']=='A'}
    interactions={}
    for metric in ('transaction_rate','timely_rate','fp_records','necessary_obligation_rate'):
        values={a:r[metric] for a,r in ablation.items()}
        interactions[metric]=None if any(v is None for v in values.values()) else values['A3']-values['A2']-values['A1']+values['A0']
    return dict(cells=cells,summary=summary,interactions=interactions,
        rule='Within each parent use the same qualified faults in both seeds and all four arms; equal parent weights. Unknown/unexposed cells are excluded jointly and explicitly, never scored as pass or miss. Descriptive, no significance claim.')


def search_analysis(protocol,execution):
    runs=[];paid=read(Path(protocol['acquisitions'])/'protocol.json')
    def gap_type(g):return g['parent_bug']+'|'+g['kind']+'|'+g['obligation']
    baseline_types={cid:{gap_type(g) for g in evidence_gaps(read(path)['measurement']['evidence']).values()} for cid,path in paid['baselines'].items()}
    for e in protocol['entries']:
        if e['strategy']!='R1':continue
        folder=execution/e['id'];records=[read(p) for p in sorted((folder/'acquisition').glob('query*/acquisition.json'))]
        if not records:records=[read(e['state'])['first_acquisition']]
        points=[dict(queries=0,seconds=0,gap_ids=[],new_gap_count=0,new_obligation_gap_types=[])];gaps=set();types=set();seconds=0
        for record in records:
            seconds+=record['cost']['r196_total_seconds'];gaps.update(record['new_gap_ids'])
            types.update(gap_type(g) for g in record['gap_records'] if g['gap_id'] in record['new_gap_ids'])
            types-=baseline_types[e['case_id']]
            points.append(dict(queries=len(points),seconds=seconds,gap_ids=sorted(gaps),new_gap_count=len(gaps),
                new_obligation_gap_types=sorted(types),
                critical_unknown=len(record['measurement']['critical_unknown']),candidate_sha256=record['candidate_sha256'],
                query_actual_seconds=record['cost']['r196_total_seconds'],query_predicted_seconds=record['cost']['predicted_acquisition_seconds'],
                sampled_cycles=2*len(record['query']['rows']),planning_seconds=record['cost'].get('planning_seconds'),
                scheduling_wait_seconds=record['cost'].get('shared_lock_wait_seconds',0),
                native_complete=record['measurement']['native_complete']))
        runs.append(dict(case_id=e['case_id'],seed=e['seed'],strategy=e['search'],id=e['id'],points=points,
            final_gap_ids=sorted(gaps),physical_first_query_reused=bool(records[0].get('reuse'))))
    sets={s:set().union(*(set(r['final_gap_ids']) for r in runs if r['strategy']==s)) for s in ('S0','S1','S2','S3')}
    cut_cells=[]
    for cid in protocol['case_ids']:
        for seed in protocol['seeds']:
            group={r['strategy']:r for r in runs if r['case_id']==cid and r['seed']==seed}
            cut=min(r['points'][-1]['seconds'] for r in group.values())
            cut_cells.append(dict(case_id=cid,seed=seed,common_actual_query_seconds=cut,
                checkpoints={s:max((p for p in r['points'] if p['seconds']<=cut),key=lambda p:p['queries']) for s,r in group.items()}))
    rows=[]
    for s in sets:
        selected=[r for r in runs if r['strategy']==s]
        rows.append(dict(strategy=s,paired_case_seeds=len(selected),queries=sum(r['points'][-1]['queries'] for r in selected),
            confirmed_context_gaps=len(sets[s]),exclusive_context_gaps=len(sets[s]-set().union(*(v for k,v in sets.items() if k!=s))),
            new_parent_obligation_gap_types=len(set().union(*(set(r['points'][-1]['new_obligation_gap_types']) for r in selected))),
            mean_context_gaps=mean([len(r['final_gap_ids']) for r in selected]),
            mean_common_cost_context_gaps=mean([r['checkpoints'][s]['new_gap_count'] for r in cut_cells]),
            actual_query_seconds=sum(r['points'][-1]['seconds'] for r in selected),
            unknown_queries=sum(p.get('critical_unknown',0)>0 for r in selected for p in r['points'][1:])))
    calibration=[]
    for cid in protocol['case_ids']:
        points=[p for r in runs if r['case_id']==cid for p in r['points'][1:]]
        calibration.append(dict(case_id=cid,measured_queries=len(points),
            mean_actual_seconds=mean([p['query_actual_seconds'] for p in points]),mean_predicted_seconds=mean([p['query_predicted_seconds'] for p in points]),
            mean_absolute_error_seconds=mean([abs(p['query_actual_seconds']-p['query_predicted_seconds']) for p in points]),
            sampled_cycle_lengths=sorted({p['sampled_cycles'] for p in points})))
    return dict(runs=runs,table=rows,common_cuts=cut_cells,cost_prediction_validation=calibration,
        scope='Adaptive search plus R1 refinement trajectories, same initial candidates and seeds. Context gaps are not independent bugs. Also report coarser parent+obligation+FN/FP types not already present in the public baseline; that coarse view can merge distinct temporal defects and complements rather than replaces context counts. Each completed query is charged; no result from a query crossing a cost cut is credited. Early stops retained.')


def plots(search,out):
    if os.name!='nt':
        dump(out/'plot_pending.json',dict(reason='Pinned matplotlib wheels are Windows binaries; render the saved analysis with the workspace Windows Python.'))
        return
    sys.path.insert(0,str(ROOT/'.research195_plotdeps'));os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.research195_plotcache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for s in ('S0','S1','S2','S3'):
        runs=[r for r in search['runs'] if r['strategy']==s]
        for ax,axis,grid in ((axes[0],'queries',[0,1,2]),(axes[1],'seconds',list(range(0,121,2)))):
            ys=[mean([max((p for p in r['points'] if p[axis]<=budget),key=lambda p:p['queries'])['new_gap_count'] for r in runs]) for budget in grid]
            ax.step(grid,ys,where='post',label=s)
    axes[0].set_xlabel('Completed query budget');axes[1].set_xlabel('Actual query-service seconds')
    for ax in axes:ax.set_ylabel('Mean confirmed context gaps / case-seed');ax.legend();ax.grid(alpha=.25)
    fig.suptitle('R196: same initial candidates; adaptive R1 chains; early stops retained')
    fig.tight_layout();fig.savefig(out/'search_cost_curves.png',dpi=170);plt.close(fig)


def build(prepared,execution,acceptance,cost,out):
    prepared,execution,acceptance,cost,out=map(Path,(prepared,execution,acceptance,cost,out))
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen' or read(acceptance/'outcome.json')['status']!='completed':raise ValueError('unfinished_experiment')
    out.mkdir(parents=True,exist_ok=False);protocol=read(prepared/'protocol.json');rr=trajectories(execution);aa=read(acceptance/'results.json')
    if len(rr)!=64:raise ValueError('population_changed')
    search=search_analysis(protocol,execution);pair=paired(aa);cost_analysis=read(cost/'analysis.json')
    rt=aggregate(rr,[(f'R{i}','S0',f'R{i}') for i in range(4)],aa)
    at=aggregate(rr,[('A0','S0','R1'),('A1','S3','R1'),('A2','S0','R3'),('A3','S3','R3')],aa)
    records=[];calls=[];attempt_matrix=[];initial_unknowns=[]
    for e in protocol['entries']:
        folder=execution/e['id']/'refinement';rounds=optional(folder/'rounds.json',[])
        if e['mode']=='blocked_unknown':
            initial_unknowns.append(dict(id=e['id'],reasons=reason_names(read(e['state'])['first_measurement']['critical_unknown'])))
        for index in (1,2):
            observed=next((r for r in rounds if r['round']==index),None)
            attempt_matrix.append(dict(id=e['id'],round=index,classification=classify_round(observed) if observed else 'not_attempted',
                initial_mode=e['mode'],terminal=read(folder/'outcome.json').get('termination_reason'),
                note=None if observed else 'No executed round record; initial unknown or earlier terminal condition. Not a failed modification.'))
        for r in rounds:
            decision=r.get('decision',{});guard=decision.get('component_guard',{})
            records.append(dict(id=e['id'],round=r['round'],stage=r.get('stage'),status=r.get('status'),classification=classify_round(r),
                component_guard_failed=guard.get('enabled') is True and not guard.get('passed',False),
                component_inactive=guard.get('blocked_components',[]),component_unknown=guard.get('unknown',[]),
                critical_unknown=decision.get('critical_unknown',[]),unknown_reason_names=reason_names(decision.get('critical_unknown',[])),regression=decision.get('regression',False)))
        for p in sorted(folder.glob('round*/model_call/result.json')):calls.append(dict(id=e['id'],path=str(p.resolve()),**read(p)))
    ledger=read(execution/'ledger.json');tokens=sum((c.get('prompt_tokens') or 0)+(c.get('completion_tokens') or 0) for c in calls)
    attempts=list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'))
    missing_results=[str(p.parent.resolve()) for p in attempts if not (p.parent/'result.json').exists()]
    summary=dict(status='latest_registered_experiment_completed',frozen_trajectories=len(rr),actual_model_calls=len(attempts),result_reported_calls=sum(c.get('model_calls',0) for c in calls),reserved_calls=len(ledger),authorized_limit=118,
        missing_model_result_records=missing_results,known_tokens=tokens,unknown_usage_calls=len(missing_results)+sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),
        model_phase_physical_compile_records=sum(1 for _ in execution.rglob('compile.json')),
        model_phase_physical_execution_records=sum(1 for _ in execution.rglob('execute.json')),
        first_acquisitions_reused_physical_jobs=64,
        call_statuses=dict(Counter(c['status'] for c in calls)),round_statuses=dict(Counter(r['status'] for r in records)),
        round_classifications=dict(Counter(r['classification'] for r in attempt_matrix)),
        component_gate_rejections=sum(r['component_guard_failed'] for r in records),component_finite_inactivity_proposals=sum(bool(r['component_inactive']) for r in records),
        component_unknown_proposals=sum(bool(r['component_unknown']) for r in records),accepted_rounds=sum(r['status']=='accepted' for r in records),
        blocked_initial=initial_unknowns,proposal_unknown_reasons=dict(Counter(reason for r in records for reason in r['unknown_reason_names'])),
        proposal_unknown_rounds=sum(bool(r['critical_unknown']) for r in records),
        independent_version_fault_records=len(aa),independent_unknown_records=sum(bool(r['unknown_records']) for r in aa),
        independent_full_scope_pass_records=sum(r['full_planned_transaction_scope_pass'] for r in aa),
        independent_physical_cost=read(acceptance/'physical_cost.json'),cost_checkpoint_evaluation=read(cost/'evaluation_outcome.json'),
        remaining=['General response windows and multiple outstanding transactions have native interface qualification only; no new real-RTL LLM comparison.',
            'This execution adds no new sourced historical repair beyond the existing Ibex flush sub-fix.',
            'A2/A3 test the full R3 localization/history/composition policy; this is not an isolated estimate of the local-edit operator alone. The prior R195 F/P/L isolation remains separate.',
            'The latest campaign has a two-round ceiling; fallback paths requiring a third model round are outside this registered execution.',
            'Per-parent sample size remains four designs and two seeds; no universal advantage or formal proof is inferred.'])
    tables=dict(search=search['table'],refinement=rt,ablation=at,cross_design=cross_design_table(aa),paired=pair['summary'],interactions=pair['interactions'])
    diagnostics=request_diagnostics(execution)
    for name,data in [('summary',summary),('tables',tables),('search_analysis',search),('paired_analysis',pair),('trajectory_index',rr),('round_audit',records),('attempt_matrix',attempt_matrix),('calls',calls),('cost_analysis',cost_analysis),('request_diagnostics',diagnostics)]:dump(out/(name+'.json'),data)
    plots(search,out)
    body=['<!doctype html><meta charset="utf-8"><title>REGuard R196 最新组合实验</title><style>body{font:15px/1.6 system-ui;max-width:1350px;margin:30px auto;padding:20px;color:#183047}.scroll{overflow:auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bdc9d1;padding:7px}pre{white-space:pre-wrap;background:#eef3f6;padding:16px}img{max-width:100%}</style>',
        '<h1>REGuard R196：最新组合实验与独立验收</h1><p>注册实验执行完成与验收通过分别统计。无总体优势是有效结果；unknown、未曝光和空触发均保留。</p>',
        '<p><a href="../reguard_mechanisms_20261103_r04/report.html">组件门修复、时序资格验证及正反案例</a> · <a href="summary.json">执行与限制</a> · <a href="tables.json">五类结果数据</a> · <a href="paired_analysis.json">父 Bug 配对与排除项</a></p>',
        '<p><a href="../research196_case_cards_20261104_r01/cards.html">本轮机制案例与独立验收</a> · <a href="../reguard_mechanisms_20261103_r01/report.html">历史统一入口：onehot、11 对候选及复杂 FIFO</a> · <a href="../research194_fault_augmentation_audit_20261103_r01/summary.json">历史故障族增强探索</a></p>',
        '<h2>执行账本</h2><pre>'+escape(json.dumps({k:v for k,v in summary.items() if k not in ('independent_physical_cost','remaining')},ensure_ascii=False,indent=2))+'</pre>',
        '<p><a href="request_diagnostics.json">请求增长与调用失败诊断</a>：单独计量原始 RTL、开发证据及历史组件审计的请求体开销；没有服务端错误正文时，不断言 HTTP 400 的具体原因。</p>',
        '<h2>S0–S3：证据及实际查询成本</h2><p>每条轨迹从同一初始候选开始，均使用 R1 细化；后续候选可能因证据不同而分歧。上下文缺口数不是独立 Bug 数。曲线只在完整查询结束后计入证据。</p>',table(search['table'],[(k,k) for k in search['table'][0]]),'<img src="search_cost_curves.png" alt="实际查询成本与有效上下文缺口曲线">',
        '<h2>R0–R3：修改策略</h2>',table(rt,[('method','策略'),('model_calls','调用'),('known_tokens','已知 tokens'),('accepted_rounds','接受轮数'),('accepted_local','局部接受'),('accepted_compose','组合接受'),('accepted_regenerate','再生成接受'),('regression_proposed','退化提案'),('regression_accepted','接受退化'),('interface_failures','接口/无变化'),('unknown_trajectories','轨迹未知')]),
        '<h2>A0–A3：最新 2×2 组合消融</h2><p>A0=S0R1，A1=S3R1，A2=S0R3，A3=S3R3。它们是实际轨迹的别名，不重复计费。</p>',table(at,[('method','策略'),('model_calls','调用'),('known_tokens','已知 tokens'),('accepted_rounds','接受轮数'),('independent_parent_macro_detection_rate','可用项父 Bug 平均检出率'),('independent_unknown_version_faults','未知版本×故障')]),
        '<h2>同父 Bug、两种子、同故障配对</h2><p>只在所有比较组和两个种子共同已知的故障上计算；先父案例内平均，再等权平均父案例。完整排除清单在 paired_analysis.json。</p>',table(pair['summary'],[(k,k) for k in pair['summary'][0]]),'<p>组合交互项 A3−A2−A1+A0：</p><pre>'+escape(json.dumps(pair['interactions'],indent=2))+'</pre>',
        '<h2>跨设计、跨故障独立验收</h2>',table(tables['cross_design'],[('case_id','设计'),('arm','组'),('versions','版本'),('faults','故障'),('known_version_faults','已知项'),('unknown_version_faults','未知项'),('necessary_obligation_protection_rate','必要义务保护率'),('known_transaction_misses','目标事务漏报'),('legal_fp_records','合法误报'),('unseen_faults_with_any_detection','未见故障有检出项'),('unseen_known_version_faults','未见故障已知项'),('no_exposure_queries','未曝光查询'),('full_scope_passed_version_faults','完整范围通过项')]),
        '<h2>实际共同成本截面</h2><p>截面只根据开发阶段实际成本选择，并在独立验收前封存。tokens 与服务耗时分开；后者包含查询、模型调用和提案原生回放，不包含共享基线、调度等待和编排 I/O，不能当作端到端总耗时。</p>',
        table([r for r in cost_analysis['summary'] if r['budget_label']=='minimum_observed_total'],[(k,k) for k in cost_analysis['summary'][0]]),
        '<h2>仍未完成的范围</h2><pre>'+escape(json.dumps(summary['remaining'],ensure_ascii=False,indent=2))+'</pre>']
    (out/'report.html').write_text('\n'.join(body),encoding='utf-8')
    sources=[prepared/'protocol.json',execution/'outcome.json',execution/'ledger.json',acceptance/'outcome.json',acceptance/'results.json',cost/'analysis.json']
    sources += [ROOT/'scripts'/name for name in ('research196_results.py','research196_cost_sections.py','research196_cards.py','research196_finish.py','research196_final_audit.py')]
    dump(out/'source_bindings.json',{str(p.resolve()):file_hash(p) for p in sources})
    print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('prepared','execution','acceptance','cost','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();build(a.prepared,a.execution,a.acceptance,a.cost,a.out)
