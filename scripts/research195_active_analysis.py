"""Read-only paired query/cycle cuts; crossing queries never receive credit."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

STRATEGIES=('S2','active_no_cost','active_cost')


def read(path):return json.loads(Path(path).read_text())
def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def state_at_cut(points,field,cut):
    """No interpolation or fractional credit for an over-budget query."""
    return next(p for p in reversed(points) if p[field]<=cut)


def analyze(out):
    out=Path(out);protocol=read(out/'protocol.json');complete=(out/'outcome.json').exists() and read(out/'outcome.json')['status']=='completed'
    records=[dict(read(p),acquisition_path=str(p)) for p in sorted((out/'sessions').glob('*/*/*/query*/acquisition.json'))]
    auxiliary=[read(p) for folder in ('calibration','baseline') for p in (out/folder).glob('**/acquisition.json')]
    points=[];tables=[];contexts={};first=[]
    for case in protocol['cases']:
        baseline=read(out/'baseline'/case/'acquisition.json') if (out/'baseline'/case/'acquisition.json').exists() else None
        excluded=set(baseline['gap_contexts']) if baseline else set()
        for seed in protocol['seeds']:
            for strategy in STRATEGIES:
                rr=sorted((r for r in records if (r['case_id'],r['seed'],r['strategy'])==(case,seed,strategy)),key=lambda r:r['round'])
                seen=set();fully_missed=set();cycles=0;wall=0;native=0
                pp=[dict(queries=0,sampled_cycles=0,native_seconds=0,total_seconds_excluding_lock_wait=0,new_contexts=0,new_context_ids=[],new_complete_miss_contexts=0)]
                for r in rr:
                    for key,value in r['gap_contexts'].items():contexts.setdefault(key,value)
                    new=set(r['gap_contexts'])-excluded;seen.update(new)
                    missed=set(r['temporal_detection']['transaction_missed_ids'])
                    fully_missed.update(k for k in new if any(e in missed for e in r['gap_contexts'][k]['evidence_ids']))
                    cycles+=r['cost']['observed_sampled_cycles'];native+=r['cost']['native_seconds'];wall+=r['cost']['total_wall_seconds_excluding_lock_wait']
                    pp.append(dict(queries=len(pp),sampled_cycles=cycles,native_seconds=native,total_seconds_excluding_lock_wait=wall,
                        new_contexts=len(seen),new_context_ids=sorted(seen),new_complete_miss_contexts=len(fully_missed)))
                points.append(dict(case_id=case,seed=seed,strategy=strategy,completed_queries=len(rr),points=pp))
                earliest=next((p for p in pp if p['new_contexts']),None)
                first.append(dict(case_id=case,seed=seed,strategy=strategy,first_new_context=earliest))
    cost_curves=[];query_curves=[];paired=[]
    units=[(c,s) for c in protocol['cases'] for s in protocol['seeds']]
    for case,seed in units:
        group={p['strategy']:p for p in points if (p['case_id'],p['seed'])==(case,seed)}
        support=min(p['points'][-1]['sampled_cycles'] for p in group.values())
        for cut in protocol['analysis']['cycle_grid']:
            if cut>support:continue
            for strategy,p in group.items():
                state=state_at_cut(p['points'],'sampled_cycles',cut)
                cost_curves.append(dict(case_id=case,seed=seed,strategy=strategy,cycle_cut=cut,**state))
        for cut in protocol['analysis']['equal_query_cuts']:
            if cut>min(p['completed_queries'] for p in group.values()):continue
            for strategy,p in group.items():query_curves.append(dict(case_id=case,seed=seed,strategy=strategy,query_cut=cut,**state_at_cut(p['points'],'queries',cut)))
        for comparator in ('S2','active_no_cost'):
            method=group['active_cost']['points'][-1];base=group[comparator]['points'][-1]
            at_method=state_at_cut(group['active_cost']['points'],'sampled_cycles',support);at_base=state_at_cut(group[comparator]['points'],'sampled_cycles',support)
            paired.append(dict(case_id=case,parent_bug=case+'/artificial',seed=seed,method='active_cost',comparator=comparator,
                common_actual_cycle_cut=support,context_difference_at_common_cycle_cut=at_method['new_contexts']-at_base['new_contexts'],
                completed_queries_at_cut={s:state_at_cut(group[s]['points'],'sampled_cycles',support)['queries'] for s in ('active_cost',comparator)},
                equal_query_count=method['queries']==base['queries'],final_query_context_difference=method['new_contexts']-base['new_contexts'],
                final_actual_cycle_difference=method['sampled_cycles']-base['sampled_cycles'],final_native_seconds_difference=method['native_seconds']-base['native_seconds']))
    for strategy in STRATEGIES:
        rr=[r for r in records if r['strategy']==strategy];uu=[u for u in points if u['strategy']==strategy]
        all_ids=set().union(*(set(u['points'][-1]['new_context_ids']) for u in uu));others=set().union(*(set(u['points'][-1]['new_context_ids']) for u in points if u['strategy']!=strategy))
        tables.append(dict(strategy=strategy,actual_queries=len(rr),native_compiles=sum(r['cost']['native_compile_attempts'] for r in rr),
            native_executions=sum(r['cost']['native_execution_attempts'] for r in rr),actual_sampled_cycles=sum(r['cost']['observed_sampled_cycles'] for r in rr),
            submitted_sampled_cycles=sum(r['cost']['submitted_sampled_cycles'] for r in rr),native_seconds=sum(r['cost']['native_seconds'] for r in rr),
            planning_seconds=sum(r['cost']['planning_seconds'] for r in rr),lock_wait_seconds=sum(r['cost']['lock_wait_seconds'] for r in rr),
            mean_new_contexts_per_case_seed=statistics.mean(u['points'][-1]['new_contexts'] for u in uu),pooled_distinct_new_contexts=len(all_ids),exclusive_context_ids=sorted(all_ids-others),
            critical_unknown=sum(len(r['measurement']['critical_unknown']) for r in rr),unknown_evidence_records=sum(sum(e['status']=='unknown' for e in r['measurement']['evidence']) for r in rr),
            native_semantic_unknown_queries=sum(not r['semantic_native_consistent'] for r in rr),
            late_detected_transactions=sum(len(r['temporal_detection']['late_detected_ids']) for r in rr),
            actual_native_candidate_disagreement_queries=sum(r['actual_native_candidate_disagreement'] for r in rr),
            selected_lengths=[len(r['query']['rows']) for r in rr],cache_reused_native_jobs=0,model_calls=0))
    macro_curves=[]
    for cut in protocol['analysis']['cycle_grid']:
        for strategy in STRATEGIES:
            rr=[r for r in cost_curves if r['strategy']==strategy and r['cycle_cut']==cut]
            if len(rr)!=len(units):continue
            macro_curves.append(dict(strategy=strategy,cycle_cut=cut,paired_case_seed_units=len(rr),mean_new_contexts=statistics.mean(r['new_contexts'] for r in rr),
                mean_queries_completed=statistics.mean(r['queries'] for r in rr)))
    diagnostics=[]
    for p in sorted((out/'sessions').glob('*/*/*/selection*.json')):
        r=read(p);values=[x['semantic_discrimination'] for x in r['ranked'] if x['semantic_discrimination'] is not None]
        diagnostics.append(dict(path=str(p),candidate_semantic_scores_saturated=bool(values) and len(set(values))==1,
            minimum_semantic_score=min(values) if values else None,maximum_semantic_score=max(values) if values else None))
    result=dict(status='completed' if complete else 'partial_not_a_completed_comparison',tables=tables,
        physical_auxiliary_cost=dict(native_jobs=sum(r['cost']['native_execution_attempts'] for r in auxiliary),native_seconds=sum(r['cost']['native_seconds'] for r in auxiliary),
            sampled_cycles=sum(r['cost']['observed_sampled_cycles'] for r in auxiliary),shared_public_baseline_logical_jobs=2*len(points)),
        source_protocol_sha256=hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest(),paired_comparisons=paired,model_calls=0,new_native_jobs=0,
        limitations=['Initial assertions and contrasting candidates remain handwritten and frozen; no refinement or independent generalization is claimed.',
            'Cycle-cost savings are not wall-clock speedups. Every main query is physically compiled and executed; no main result reuse.',
            'Two artificial parent Bugs and two paired seeds are a bounded demonstration, not broad significance evidence.',
            'Context equality is observed-prefix equality, not formal behavioral equivalence. First-violation gaps include late detections; complete misses are separate.',
            'At a cycle cut, a query that crosses the budget contributes no evidence. Query count, planning overhead, lock wait and actual native seconds remain explicit.'])
    for name,value in [('analysis.json',result),('unit_cost_curves.json',points),('paired_cycle_cuts.json',cost_curves),('paired_query_cuts.json',query_curves),
        ('mean_cycle_curve.json',macro_curves),('first_discovery_cost.json',first),('gap_context_index.json',contexts),('planning_diagnostics.json',diagnostics)]:dump(out/name,value)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(1,2,figsize=(11,4.5))
        for strategy in STRATEGIES:
            rr=[r for r in macro_curves if r['strategy']==strategy]
            axes[0].step([r['cycle_cut'] for r in rr],[r['mean_new_contexts'] for r in rr],where='post',label=strategy)
            qq=[]
            for cut in protocol['analysis']['equal_query_cuts']:
                r=[x for x in query_curves if x['strategy']==strategy and x['query_cut']==cut]
                if len(r)==len(units):qq.append((cut,statistics.mean(x['new_contexts'] for x in r)))
            axes[1].step([q[0] for q in qq],[q[1] for q in qq],where='post',label=strategy)
        for ax in axes:ax.set_ylabel('Mean new confirmed gap contexts');ax.grid(alpha=.25);ax.legend()
        axes[0].set_xlabel('Actual sampled cycles per case/seed (paired cut)');axes[1].set_xlabel('Actual submitted queries per case/seed')
        fig.suptitle('Variable-cost schedules: paired complete-query evidence coverage')
        fig.text(.5,.01,'First-violation/FP contexts; late detections separate. Native seconds and all auxiliary costs are in analysis.json.',ha='center',fontsize=8)
        fig.tight_layout(rect=(0,.04,1,.95));fig.savefig(out/'paired_cost_curves.png',dpi=160);plt.close(fig)
    except ImportError:dump(out/'plot_status.json',dict(status='matplotlib_unavailable',json_curves_complete=True))
    print(json.dumps(dict(status=result['status'],queries=len(records),main_native_jobs=sum(t['native_executions'] for t in tables))))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);analyze(parser.parse_args().out)
