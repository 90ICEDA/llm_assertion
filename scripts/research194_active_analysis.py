"""Read-only experimental analysis; writes separate derived tables and curves."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import research194_active_search as active
import research194_metrics
from research194_metrics import temporal_detection


def context_gaps(measurement):
    """Observed trace-context equivalence, never a claim of formal equivalence.

    Whole-query hashing distinguishes identical transaction prefixes. For this
    supplemental statistic, keep the actual oracle transaction segment through
    the first violation, stripping only absolute cycle numbers. Do not merge
    different obligations, fault variants, parents, or observed signal values.
    """
    gaps=active.gaps(measurement['evidence']);result={}
    for key,gap in gaps.items():
        events=[e for e in measurement['evidence'] if e['evidence_id']==gap['evidence_id'] and e['status']=='confirmed']
        ev=next(e for e in events if (e.get('counted_target',False) if gap['kind']=='FN' else any(a['failure'] for a in e.get('assertions',[]))))
        job=next(j for j in measurement['executions'] if j['query_id']==ev['query_id'] and j['variant']==ev['variant'])
        cycle=ev['cycle'];start=ev.get('transaction',max(0,cycle-1))
        if not isinstance(start,int) or start<0 or start>cycle:start=max(0,cycle-1)
        context=[{k:v for k,v in row.items() if k!='cycle'} for row in job['trace'] if start<=row['cycle']<=cycle]
        signature=dict(parent_bug=gap['parent_bug'],variant=ev['variant'],obligation=ev['obligation'],kind=gap['kind'],observed_transaction_prefix=context)
        context_id=gap['kind']+':'+active.sem.digest(signature)
        result.setdefault(context_id,dict(context_id=context_id,signature=signature,evidence_ids=[],transaction_ids=[]))
        result[context_id]['evidence_ids'].append(ev['evidence_id']);result[context_id]['transaction_ids'].append(ev['transaction_id'])
    return result


def analyze(root):
    protocol=json.loads((root/'protocol.json').read_text());records=[]
    for path in sorted((root/'sessions').glob('*/*/S*/query*/acquisition.json')):
        record=json.loads(path.read_text());record['source_path']=str(path);records.append(record)
    strategies=protocol['strategies'];units=[(case,seed) for case in protocol['cases'] for seed in protocol['seeds']]
    allgaps={s:set().union(*(set(r['gap_ids']) for r in records if r['strategy']==s)) for s in strategies}
    newgaps={s:set().union(*(set(r['cumulative_new_gap_ids']) for r in records if r['strategy']==s)) for s in strategies}
    tables=[];unitrows=[];costcurve=[];first=[];links=[];context_units=[];context_curve=[];context_index={}
    baseindex=json.loads((root/'baseline_index.json').read_text())
    baseline_context={}
    for unit,path in baseindex.items():
        p=Path(path)
        if not p.exists():p=root/'baselines'/p.parent.name/'baseline.json'
        baseline_context[unit]=set(context_gaps(json.loads(p.read_text())['measurement']))
    for strategy in strategies:
        rows=[r for r in records if r['strategy']==strategy];others=set().union(*(newgaps[s] for s in strategies if s!=strategy))
        gaps_by_id={g['gap_id']:g for r in rows for g in r['gap_records']}
        confirmed_ids={e['evidence_id'] for r in rows for e in r['evidence'] if e['status']=='confirmed'}
        unknown_ids={e['evidence_id'] for r in rows for e in r['evidence'] if e['status']=='unknown'}
        tables.append(dict(strategy=strategy,queries=len(rows),native_compile_attempts=sum(r['cost']['native_compile_attempts'] for r in rows),
            native_execution_attempts=sum(r['cost']['native_execution_attempts'] for r in rows),
            native_seconds=sum(r['cost']['native_seconds'] for r in rows),planning_seconds=sum(r['cost']['planning_seconds'] for r in rows),
            summed_acquisition_wall_seconds_including_planning=sum(r['cost']['acquisition_wall_seconds']+r['cost']['planning_seconds'] for r in rows),
            confirmed_evidence=len(confirmed_ids),unknown_evidence=len(unknown_ids),critical_unknown=sum(len(r['measurement']['critical_unknown']) for r in rows),
            all_distinct_gaps=len(allgaps[strategy]),new_distinct_gaps=len(newgaps[strategy]),exclusive_new_gap_ids=sorted(newgaps[strategy]-others),
            new_fn=sum(g.startswith('FN:') for g in newgaps[strategy]),new_fp=sum(g.startswith('FP:') for g in newgaps[strategy]),
            new_gap_parents=sorted({gaps_by_id[g]['parent_bug'] for g in newgaps[strategy]}),
            new_gap_transactions=len({gaps_by_id[g]['transaction_id'] for g in newgaps[strategy]}),
            actual_native_xor_queries=sum(any(v['actual_native_xor'] for v in r['native_prediction_validation']) for r in rows),
            semantic_native_unknown_jobs=sum(v['semantic_validation']['status']!='confirmed_semantics' for r in rows for v in r['native_prediction_validation']),model_calls=0))
        for case,seed in units:
            rr=sorted((r for r in rows if r['case_id']==case and r['seed']==seed),key=lambda r:r['round'])
            seen=set();context_seen=set();cost=0;points=[dict(native_execution_cost=0,new_gaps=0,new_gap_ids=[])];context_points=[dict(native_execution_cost=0,new_gaps=0,new_gap_ids=[])]
            first_cost=None
            for r in rr:
                cost+=r['cost']['native_execution_attempts'];seen.update(r['new_gap_ids'])
                if first_cost is None and seen:first_cost=cost
                points.append(dict(native_execution_cost=cost,new_gaps=len(seen),new_gap_ids=sorted(seen)))
                contexts=context_gaps(r['measurement'])
                for key,value in contexts.items():
                    if key not in context_index:context_index[key]=value
                    else:
                        for field in ('evidence_ids','transaction_ids'):context_index[key][field]=sorted(set(context_index[key][field])|set(value[field]))
                context_seen.update(set(contexts)-baseline_context[f'{case}/{seed}'])
                context_points.append(dict(native_execution_cost=cost,new_gaps=len(context_seen),new_gap_ids=sorted(context_seen)))
                links.append(dict(task_id=r['task_id'],case_id=case,seed=seed,strategy=strategy,round=r['round'],candidate_sha256=r['candidate_sha256'],
                    query_id=r['query']['id'],evidence_ids=r['evidence_ids'],new_gap_ids=r['new_gap_ids'],acquisition_path=r['source_path'],
                    use_for_refinement='only reveal this acquisition when its round is reached; later acquisition must not leak into round0'))
            unitrows.append(dict(case_id=case,seed=seed,strategy=strategy,points=points))
            context_units.append(dict(case_id=case,seed=seed,strategy=strategy,points=context_points))
            first.append(dict(case_id=case,seed=seed,strategy=strategy,first_new_gap_native_cost=first_cost,exhausted_without_new_gap=first_cost is None and len(rr)==2))
        for cost in (0,2,4):
            relevant=[u for u in unitrows if u['strategy']==strategy];states=[]
            for u in relevant:states.append(next(p for p in reversed(u['points']) if p['native_execution_cost']<=cost))
            pooled=set().union(*(set(p['new_gap_ids']) for p in states))
            costcurve.append(dict(strategy=strategy,actual_native_execution_cost_per_unit=cost,paired_unit_count=len(states),
                mean_new_distinct_gaps_per_case_seed=statistics.mean(p['new_gaps'] for p in states),pooled_new_distinct_gaps=len(pooled),
                pooled_unit_note='pooled deduplicates identical transaction+obligation IDs across seeds; mean weights paired case/seed units equally'))
            ctxstates=[next(p for p in reversed(u['points']) if p['native_execution_cost']<=cost) for u in context_units if u['strategy']==strategy]
            context_curve.append(dict(strategy=strategy,actual_native_execution_cost_per_unit=cost,paired_unit_count=len(ctxstates),
                mean_new_distinct_gaps_per_case_seed=statistics.mean(p['new_gaps'] for p in ctxstates),pooled_new_distinct_gaps=len(set().union(*(set(p['new_gap_ids']) for p in ctxstates))),
                count_unit='cycle-normalized observed transaction prefix + parent + obligation + fault variant + gap kind'))
    context_sets={s:set().union(*(set(u['points'][-1]['new_gap_ids']) for u in context_units if u['strategy']==s)) for s in strategies}
    for row in tables:
        s=row['strategy'];row['new_trace_context_distinct_gaps']=len(context_sets[s])
        row['exclusive_new_trace_context_gap_ids']=sorted(context_sets[s]-set().union(*(context_sets[o] for o in strategies if o!=s)))
        timing=[temporal_detection(r['measurement']) for r in records if r['strategy']==s]
        for field in ('timely_detected_ids','transaction_detected_ids','late_detected_ids','transaction_missed_ids'):
            row['pooled_'+field+'_count']=len(set().union(*(set(t[field]) for t in timing)))
    diagnostics=[]
    for case,seed in units:
        rr=[r for r in records if r['case_id']==case and r['seed']==seed]
        summary={s:set().union(*(set(r['new_gap_ids']) for r in rr if r['strategy']==s)) for s in strategies}
        contexts={s:set().union(*(set(u['points'][-1]['new_gap_ids']) for u in context_units if u['case_id']==case and u['seed']==seed and u['strategy']==s)) for s in strategies}
        active_rows=[r for r in rr if r['strategy']=='S3']
        diagnostics.append(dict(case_id=case,seed=seed,gaps_by_strategy={s:len(summary[s]) for s in strategies},
            s3_minus_s0=len(summary['S3'])-len(summary['S0']),s3_minus_s2=len(summary['S3'])-len(summary['S2']),
            trace_context_gaps_by_strategy={s:len(contexts[s]) for s in strategies},s3_minus_s0_trace_context=len(contexts['S3'])-len(contexts['S0']),s3_minus_s2_trace_context=len(contexts['S3'])-len(contexts['S2']),
            s3_query_families=[r['query']['family'] for r in active_rows],
            semantic_discrimination_saturated=bool(active_rows) and all(len({x['semantic_discrimination'] for x in r['selection']['ranked']})==1 for r in active_rows),
            no_marginal_gain_queries=[r['query']['id'] for r in active_rows if not r['new_gap_ids']],
            hypothesis_not_realized_queries=[r['query']['id'] for r in active_rows if next(x for x in r['selection']['ranked'] if x['query_id']==r['query']['id'])['semantic_discrimination']>0 and not any(v['actual_native_xor'] for v in r['native_prediction_validation'])]))
    examples=[]
    for mode in ('positive','semantic_increment','failure'):
        comparator_name='S2' if mode=='semantic_increment' else 'S0'
        improvement_field='s3_minus_s2_trace_context' if mode=='semantic_increment' else 's3_minus_s0_trace_context'
        eligible=[d for d in diagnostics if d[improvement_field]>0] if mode!='failure' else [d for d in diagnostics if d['semantic_discrimination_saturated'] or d['hypothesis_not_realized_queries'] or d['no_marginal_gain_queries']]
        if not eligible:
            examples.append(dict(kind=mode,status='no_qualifying_observed_example'));continue
        chosen=sorted(eligible,key=lambda d:(-d[improvement_field] if mode!='failure' else d['s3_minus_s2_trace_context'],d['case_id'],d['seed']))[0]
        rr=[r for r in records if r['case_id']==chosen['case_id'] and r['seed']==chosen['seed'] and r['strategy']=='S3']
        r=next((r for r in rr if (r['new_gap_ids'] if mode!='failure' else not r['new_gap_ids'])),rr[0])
        target_ids={k.split(':',1)[1] for k in r['new_gap_ids']}
        if mode!='failure':
            comparator=set().union(*(set(u['points'][-1]['new_gap_ids']) for u in context_units if u['case_id']==chosen['case_id'] and u['seed']==chosen['seed'] and u['strategy']==comparator_name))
            public=baseline_context[f'{chosen["case_id"]}/{chosen["seed"]}']
            for possible in rr:
                contexts=context_gaps(possible['measurement']);unique=set(contexts)-comparator-public
                if unique:
                    r=possible;target_ids={eid for key in unique for eid in contexts[key]['evidence_ids']};break
        ev=next((e for e in r['evidence'] if e['evidence_id'] in target_ids),next((e for e in r['evidence'] if e['status']=='confirmed' and e['label']=='violation'),None))
        waveform=[]
        if ev:
            job=next(j for j in r['measurement']['executions'] if j['variant']==ev['variant'])
            waveform=[row for row in job['trace'] if abs(row['cycle']-ev['cycle'])<=3]
        examples.append(dict(kind=mode,comparator=comparator_name,selection_rule='largest paired trace-context deduplicated gain vs comparator; or saturated/no-marginal/hypothesis-not-realized example, deterministic tie break',
            diagnostics=chosen,task_id=r['task_id'],source_acquisition=r['source_path'],original_sva=protocol['initial_candidates'][r['case_id']],
            query_goal=next(x for x in r['selection']['ranked'] if x['query_id']==r['query']['id']),evidence=ev,key_waveform=waveform,
            native_validation=r['native_prediction_validation'],refinement_link='evidence_id + task_id joins later local-refinement proposal and independent acceptance; no improvement inferred from discovery alone'))
    result=dict(complete=len(records)==64,tables=tables,paired_units=len(units),cost_curve=costcurve,first_discovery=first,mechanism_diagnostics=diagnostics,
        analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        analysis_dependencies_sha256={'research194_metrics.py':hashlib.sha256(Path(research194_metrics.__file__).read_bytes()).hexdigest()},
        trace_context_dedup_status='Supplemental post-registration accounting audit, never used in query selection. Original transaction-instance metrics are preserved. Observed prefix equality is not formal behavioral equivalence.',
        source_protocol=str(root/'protocol.json'),source_records=len(records),model_calls=0,
        limitations=['Three designs use explicit artificial obligation faults on real project RTL; Ibex is a historical flush sub-fix at the decoder boundary, not whole CPU.',
            'Same fixed public candidate pool and submitted-query budget. The two seeds randomize selection; stimuli are identical for these predeclared seeds.',
            'First violation per transaction and obligation is the detection unit. Unique parent Bugs remain a separate count.',
            'Semantic witnesses assume hypothetical output values and are planning hypotheses only; actual RTL traces and independent monitors establish evidence.',
            'Search gap discovery alone is not SVA improvement. Follow evidence_links into refinement and frozen held-out acceptance.',
            'No native formal proof; finite simulation and supported-expression interpreter. Unknowns remain separate.'])
    active.dump(root/'analysis.json',result);active.dump(root/'paired_cost_curve.json',costcurve)
    active.dump(root/'paired_unit_curves.json',unitrows);active.dump(root/'first_discovery_cost.json',first)
    active.dump(root/'evidence_links.json',links)
    active.dump(root/'mechanism_examples.json',examples)
    active.dump(root/'trace_context_gap_index.json',context_index);active.dump(root/'trace_context_cost_curve.json',context_curve)
    active.dump(root/'trace_context_unit_curves.json',context_units)
    context_first=[dict(case_id=u['case_id'],seed=u['seed'],strategy=u['strategy'],first_new_gap_native_cost=next((p['native_execution_cost'] for p in u['points'] if p['new_gaps']),None),
        observed_budget=u['points'][-1]['native_execution_cost'],final_new_gaps=u['points'][-1]['new_gaps']) for u in context_units]
    paired=[]
    for comparator in ('S0','S1','S2'):
        unit_comparisons=[]
        for case,seed in units:
            a=next(u for u in context_first if u['case_id']==case and u['seed']==seed and u['strategy']=='S3')
            b=next(u for u in context_first if u['case_id']==case and u['seed']==seed and u['strategy']==comparator)
            ac,bc=a['first_new_gap_native_cost'],b['first_new_gap_native_cost']
            outcome='both_no_new_gap' if ac is None and bc is None else 'S3_earlier_within_budget' if bc is None or ac is not None and ac<bc else 'comparator_earlier_within_budget' if ac is None or bc<ac else 'tie'
            unit_comparisons.append(dict(case_id=case,seed=seed,first_discovery=outcome,final_gap_difference=a['final_new_gaps']-b['final_new_gaps']))
        paired.append(dict(comparator=comparator,units=unit_comparisons,statistical_note='Paired descriptive comparison; two seeds per design are not independent parent Bugs. Missing event costs are censored, not filled with successful discovery.'))
    active.dump(root/'trace_context_first_discovery_cost.json',context_first);active.dump(root/'trace_context_paired_comparisons.json',paired)
    active.dump(root/'transaction_detection_timing.json',[dict(task_id=r['task_id'],round=r['round'],candidate_sha256=r['candidate_sha256'],**temporal_detection(r['measurement'])) for r in records])
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);args=ap.parse_args()
    result=analyze(args.root.resolve());print(json.dumps(dict(complete=result['complete'],tables=result['tables'])))


if __name__=='__main__':main()
