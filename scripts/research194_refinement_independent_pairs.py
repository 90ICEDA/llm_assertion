"""Read held-out results ONLY after the campaign declares completion.

Within-case/seed/fault pairing is descriptive. R3-R0 compares entire policies;
R3-R2 holds history retention closer but still changes localization/composition.
"""
import argparse
from collections import defaultdict
from pathlib import Path
from research194_refinement_posthoc import read,dump


def fine_fp(measurement):
    return {(e.get('query_id'),e.get('variant'),e.get('cycle'),e.get('obligation'))
            for e in measurement.get('evidence',[]) if e.get('status')=='confirmed'
            and e.get('label')=='legal' and any(a.get('failure') for a in e.get('assertions',[]))}


def compare(a,b):
    ta=set(a.get('targets',[]));tb=set(b.get('targets',[]));common=ta&tb
    result=dict(common_targets=sorted(common),r3_only_targets=sorted(ta-tb),comparator_only_targets=sorted(tb-ta),
        r3_unknown=a.get('critical_unknown',[]),comparator_unknown=b.get('critical_unknown',[]),
        reference_pair_complete=all(m.get('native_complete') is True and m.get('reference_complete') is True
            and not m.get('critical_unknown') for m in (a,b)),
        r3_false_positive_coarse_ids=sorted({e['id'] for e in a.get('false_positives',[])}),
        comparator_false_positive_coarse_ids=sorted({e['id'] for e in b.get('false_positives',[])}))
    for label,key in [('timely','detected_ids'),('any_cycle','transaction_detected_ids')]:
        da=set(a.get(key,[]))&common;db=set(b.get(key,[]))&common
        result[label]=dict(r3_detected_ids=sorted(da),comparator_detected_ids=sorted(db),
            gained_ids=sorted(da-db),lost_ids=sorted(db-da),both_detected_ids=sorted(da&db),
            both_missed_ids=sorted(common-da-db))
    fa=fine_fp(a);fb=fine_fp(b)
    result['legal_alarm_pair']=dict(r3_units=len(fa),comparator_units=len(fb),
        added=sorted(fa-fb,key=str),removed=sorted(fb-fa,key=str))
    result['eligible_comparable']=bool(common) and ta==tb and result['reference_pair_complete']
    result['exclusion_reasons']=(['unknown_or_incomplete_native_reference'] if not result['reference_pair_complete'] else [])
    if ta!=tb:result['exclusion_reasons'].append('target_set_mismatch')
    if not common:result['exclusion_reasons'].append('no_common_confirmed_targets')
    return result


def analyze(campaign,out):
    root=Path(campaign)/'independent'
    marker=read(root/'outcome.json',{})
    if marker.get('status')!='completed':
        raise RuntimeError('independent_not_completed: no result index or projection read')
    rows=read(root/'results.json')
    if not isinstance(rows,list):raise ValueError('independent_index_schema')
    index={}
    for row in rows:
        # Results contain frozen entry metadata; no hidden stimulus is imported.
        entry=row.get('entry',{}) if isinstance(row.get('entry'),dict) else row
        get=lambda k:row.get(k,entry.get(k))
        if get('role')=='initial_control' or get('search_strategy')!='S0':continue
        key=(get('case_id'),get('seed'),get('strategy'),get('fault'))
        if key in index:raise ValueError('duplicate_frozen_identity')
        index[key]=row
    mappings={};measurements={}
    def measurement(row):
        entry=row.get('entry',{}) if isinstance(row.get('entry'),dict) else row
        case=row.get('case_id',entry.get('case_id'));sha=row.get('candidate_sha256',entry.get('candidate_sha256'))
        if case not in mappings:mappings[case]=read(root/case/'version_mapping.json')
        mapping=mappings[case]
        keys=mapping.get('keys') if isinstance(mapping,dict) else None
        if not isinstance(keys,list):raise ValueError('version_mapping_schema')
        pos=keys.index(sha);path=root/case/row['fault']/('projection'+str(pos)+'.json')
        if path not in measurements:measurements[path]=read(path)
        if measurements[path] is None:raise ValueError('missing_projection:'+str(path))
        required={'targets','detected_ids','transaction_detected_ids','false_positives','critical_unknown'}
        if not required<=set(measurements[path]):raise ValueError('projection_metric_schema:'+str(path))
        return measurements[path],str(path)
    def development_status(row):
        entry=row.get('entry',{}) if isinstance(row.get('entry'),dict) else row
        folder=Path(row.get('folder',entry.get('folder','')))
        if not folder.is_absolute():folder=Path(campaign).resolve().parent.parent/folder
        outcome=read(folder/'outcome.json',{})
        if outcome.get('status')!='frozen':raise ValueError('missing_frozen_development_outcome:'+str(folder))
        rounds=read(folder/'rounds.json',[]) or []
        return dict(causal_comparison_eligible=outcome.get('causal_comparison_eligible') is True,
            response_truncated=any(r.get('model',{}).get('status')=='response_truncated' for r in rounds),
            proposal_or_acquisition_unknown=any(r.get('decision',{}).get('critical_unknown') or r.get('status') in ('unknown_acquisition_or_history','infrastructure_interrupted') for r in rounds),
            actual_model_calls=outcome.get('actual_model_calls'),source_folder=str(folder))
    pairs=[]
    for (case,seed,strategy,fault),row in sorted(index.items(),key=str):
        if strategy!='R3':continue
        for comparator in ('R2','R0'):
            other=index.get((case,seed,comparator,fault))
            if other is None:raise ValueError('missing_paired_identity')
            a,ap=measurement(row);b,bp=measurement(other)
            pa=development_status(row);pb=development_status(other)
            comparison=compare(a,b)
            strict_reasons=list(comparison['exclusion_reasons'])
            for label,development in [('R3',pa),(comparator,pb)]:
                if not development['causal_comparison_eligible']:strict_reasons.append(label+'_development_causal_ineligible')
                if development['response_truncated']:strict_reasons.append(label+'_budget_truncation')
                if development['proposal_or_acquisition_unknown']:strict_reasons.append(label+'_proposal_or_acquisition_unknown')
            pairs.append(dict(case_id=case,seed=seed,fault=fault,comparison='R3_vs_'+comparator,
                r3_projection=ap,comparator_projection=bp,r3_development=pa,comparator_development=pb,
                strict_execution_eligible=not strict_reasons,strict_exclusion_reasons=strict_reasons,
                **comparison))
    def aggregate_rows(selected):
        aggregate=defaultdict(lambda:dict(paired_faults=0,common_targets=0,timely_gained=0,timely_lost=0,
            any_cycle_gained=0,any_cycle_lost=0,unknown_pairs=0,legal_alarms_added=0,legal_alarms_removed=0))
        unique_alarms=defaultdict(lambda:dict(added=set(),removed=set()))
        for pair in selected:
            r=aggregate[(pair['case_id'],pair['comparison'])];r['paired_faults']+=1;r['common_targets']+=len(pair['common_targets'])
            for mode in ('timely','any_cycle'):
                for direction in ('gained','lost'):r[mode+'_'+direction]+=len(pair[mode][direction+'_ids'])
            r['unknown_pairs']+=not pair['reference_pair_complete']
            r['legal_alarms_added']+=len(pair['legal_alarm_pair']['added']);r['legal_alarms_removed']+=len(pair['legal_alarm_pair']['removed'])
            for direction in ('added','removed'):
                unique_alarms[(pair['case_id'],pair['comparison'])][direction].update(tuple(x) for x in pair['legal_alarm_pair'][direction])
        return [dict(case_id=k[0],comparison=k[1],**v,
            unique_input_legal_alarms_added=len(unique_alarms[k]['added']),
            unique_input_legal_alarms_removed=len(unique_alarms[k]['removed'])) for k,v in aggregate.items()]
    result=dict(status='completed_read_only',pairs=pairs,
        registered_pair_rows=len(pairs),eligible_pair_rows=sum(p['eligible_comparable'] for p in pairs),
        strict_pair_rows=sum(p['strict_execution_eligible'] for p in pairs),
        strict_parent_cases=sorted({p['case_id'] for p in pairs if p['strict_execution_eligible']}),
        by_parent_case_eligible_only=aggregate_rows([p for p in pairs if p['eligible_comparable']]),
        by_parent_case_strict_execution=aggregate_rows([p for p in pairs if p['strict_execution_eligible']]),
        all_pairs_descriptive_not_primary=aggregate_rows(pairs),
        excluded_from_primary=[dict(case_id=p['case_id'],seed=p['seed'],fault=p['fault'],comparison=p['comparison'],reasons=p['exclusion_reasons']) for p in pairs if not p['eligible_comparable']],
        excluded_from_strict=[dict(case_id=p['case_id'],seed=p['seed'],fault=p['fault'],comparison=p['comparison'],reasons=p['strict_exclusion_reasons']) for p in pairs if not p['strict_execution_eligible']],
        notes=['Target unit is fault/transaction/obligation, not failing cycle.',
               'by_parent_case counts paired evaluations across seeds; repeating one fault-target under two seeds does not create two independent parent Bugs. Seed-level rows are retained for paired macro analysis.',
               'legal_alarms_added/removed are paired evaluation sums; the same correct input is replayed for multiple fault variants. unique_input_legal_alarms_* deduplicates query/variant/cycle/obligation across faults and seeds within each parent/comparison, without counting these as distinct failures.',
               'Unknown pairs remain in the registered population; observed misses are not interpreted as proven misses when reference is incomplete.',
               'Primary eligible-only summary requires completed native/reference results and equal nonempty target sets; all mismatched/unknown pairs remain explicit detail.',
               'Budget-truncated model generations and unknown stopped trajectories retain their frozen versions in ITT; strict_execution is a separate sensitivity subset excluding truncation, proposal/acquisition unknown and development causal-ineligible arms.',
               'R3 vs R0 measures the entire policy difference, not localization alone.',
               'R3 vs R2 retains history in both arms but still combines localization, constrained edits and assertion composition.',
               'Gained/lost counts restrict both versions to shared confirmed targets; target mismatches are listed separately.'])
    dump(Path(out)/'independent_refinement_pairs.json',result)
    print(dict(status=result['status'],paired_rows=len(pairs)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.campaign,a.out)
