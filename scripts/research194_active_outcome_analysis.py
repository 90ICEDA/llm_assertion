"""Posthoc paired search -> edit -> frozen independent outcome accounting.

This program never calls a model, simulator, query generator or held-out runner.
It reads independent grades only AFTER their completed outcome marker exists.
Pairwise effects are descriptive: intention-to-treat retains assigned frozen
outcomes, while a separate strict view requires normal trajectory completion.
Both require explicit common-test eligibility. Parent Bugs, not cycles, are the
aggregation unit. The analysis cannot establish single-waveform causation.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import time

import research194_case_cards as cards
from research194_metrics import temporal_detection
import research194_report as report

ROOT=Path(__file__).resolve().parents[1]
STRATEGIES=('S0','S1','S2','S3')
CASES=('arbiter','counter','uart','ibex_flush')
SEEDS=(19407,19419)


def read(path,default=None):return report.read(Path(path),default)
def dump(path,value):report.dump(Path(path),value)
def norm(path):return str(path).replace('\\','/').rstrip('/')


def qualify_common_fault(grades):
    """Do not promote unexposed, unknown or mismatched populations to success."""
    reasons=[]
    if set(grades)!=set(STRATEGIES):reasons.append('missing_strategy_grade')
    if any(not g.get('native_complete') for g in grades.values()):reasons.append('native_incomplete')
    if any(g.get('unknown_records') or not g.get('reference_complete') for g in grades.values()):reasons.append('unknown_reference_or_candidate_attribution')
    if any(not g.get('valid_reachable_fault') or not g.get('target_ids') for g in grades.values()):reasons.append('unexposed_or_invalid_fault')
    populations={tuple(sorted(g.get('target_ids',[]))) for g in grades.values()}
    if len(populations)>1:reasons.append('different_target_population')
    return dict(eligible=not reasons,reasons=reasons,strategies_present=sorted(grades),
        target_count=len(next(iter(populations))) if len(populations)==1 else None,
        no_exposure_queries={s:g.get('no_exposure_queries',[]) for s,g in grades.items()},
        unknown_queries={s:g.get('unknown_queries',[]) for s,g in grades.items()})


def summarize_itt(pairs):
    parents=[];population=[]
    for baseline,method in itertools.combinations(STRATEGIES,2):
        for parent in sorted({p['parent_bug'] for p in pairs}):
            expected=[p for p in pairs if (p['parent_bug'],p['method'],p['comparator'])==(parent,method,baseline)]
            valid=[p for p in expected if p['itt_eligible']]
            parents.append(dict(parent_bug=parent,method=method,comparator=baseline,expected_seed_pairs=len(expected),
                eligible_seed_pairs=len(valid),fully_paired=len(valid)==len(expected)==2,
                mean_transaction_rate_delta=statistics.mean(p['itt_transaction_rate_delta'] for p in valid) if valid else None,
                mean_timely_rate_delta=statistics.mean(p['itt_timely_rate_delta'] for p in valid) if valid else None,
                seed_pairs_with_no_loss_gain=sum(p['itt_no_loss_no_new_fp_gain'] for p in valid),
                seed_pairs_with_lost_detection=sum(bool(p['lost_ids']) for p in valid),
                seed_pairs_with_new_legal_fp=sum(bool(p.get('new_legal_fp_units_common')) for p in valid),
                seed_pairs_retained_despite_incomplete_rounds=sum(not p['eligible'] for p in valid),
                common_fault_scope_by_seed={p['seed']:p['common_faults'] for p in valid}))
        selected=[p for p in parents if (p['method'],p['comparator'])==(method,baseline)]
        balanced=[p for p in selected if p['fully_paired']]
        population.append(dict(method=method,comparator=baseline,expected_parents=len(selected),fully_paired_parents=len(balanced),
            partially_observed_or_excluded_parents=[p['parent_bug'] for p in selected if not p['fully_paired']],
            parent_macro_transaction_rate_delta=statistics.mean(p['mean_transaction_rate_delta'] for p in balanced) if balanced else None,
            parent_macro_timely_rate_delta=statistics.mean(p['mean_timely_rate_delta'] for p in balanced) if balanced else None))
    return dict(parent_summary=parents,population=population,
        definition='Intention-to-treat for assigned real-model frozen versions, including budget-truncated or interrupted trajectories with a retained version. Unknown or unequal independent target populations still cannot become passes. Shared initial candidate and model configuration remain required.')


def evidence_bridges(row):
    """Only visible evidence with native gain retained by the final candidate."""
    folder=ROOT/row['folder'];terminal=read(folder/'terminal_measurement.json',{});frozen=read(folder/'frozen.json')
    if not frozen or not terminal or terminal.get('candidate_sha256')!=row.get('frozen_sha256') or cards.cases.digest(frozen)!=row.get('frozen_sha256'):
        return dict(eligible=False,reason='final_candidate_measurement_not_bound',bridges=[])
    retained=set(temporal_detection(terminal)['transaction_detected_ids'])
    protocol=read(folder.parent/'search'/'protocol.json',{})
    baseline_queries=set(protocol.get('baseline_queries',[]))
    acquisitions=read(folder/'acquisitions.json',[]);sources={}
    for index,acq in enumerate(acquisitions):
        for ev in acq.get('evidence',[]):
            sources.setdefault(ev.get('evidence_id',ev.get('id')),[]).append(dict(acquisition_index=index,task_id=acq.get('task_id'),
                candidate_sha256=acq.get('candidate_sha256'),query_id=ev.get('query_id'),public_baseline_query=ev.get('query_id') in baseline_queries,
                status=ev.get('status'),counted_target=ev.get('counted_target',False)))
    bridges=[];visible_all=set();visible_acquired=set()
    bound_paths=[folder/name for name in ('outcome.json','terminal_measurement.json','frozen.json','acquisitions.json','rounds.json') if (folder/name).exists()]
    for rr in read(folder/'rounds.json',[]):
        rd=folder/f'round{rr["round"]:02}';request=read(rd/'request.preview.json',{})
        bound_paths.extend(p for p in (rd/'request.preview.json',rd/'current_measurement.json',rd/'proposal_native'/'measurement.json',rd/'proposal.json') if p.exists())
        messages=request.get('messages',[]);context=json.loads(messages[-1]['content']) if messages else {}
        visible={e.get('evidence_id',e.get('id')) for e in context.get('development_observations',[]) if e.get('status')=='confirmed'}
        visible_all.update(visible);visible_acquired.update(visible & set(sources))
        if rr.get('status')!='accepted':continue
        before=read(rd/'current_measurement.json',{});after=read(rd/'proposal_native'/'measurement.json',{})
        if not before or not after:continue
        proposal=read(rd/'proposal.json')
        if before.get('candidate_sha256')!=cards.cases.digest(context.get('current_assertions')) or not proposal or after.get('candidate_sha256')!=cards.cases.digest(proposal):continue
        gained=set(temporal_detection(after)['transaction_detected_ids'])-set(temporal_detection(before)['transaction_detected_ids'])
        for eid in sorted(gained & visible & retained):
            ev=next((e for e in before['evidence'] if e.get('evidence_id',e.get('id'))==eid and e.get('counted_target')),None)
            if ev is None:continue
            relevant_sources=[a for a in sources.get(eid,[]) if a['acquisition_index']<rr['round'] and a['status']=='confirmed']
            bridges.append(dict(evidence_id=eid,obligation=ev['obligation'],round=rr['round'],
                present_in_actual_model_request=True,native_before_detected=False,native_after_detected=True,retained_by_final_candidate=True,
                acquisition_sources=relevant_sources,
                newly_acquired_nonpublic_evidence=bool(protocol) and any(not a['public_baseline_query'] for a in relevant_sources),
                public_baseline_status_known=bool(protocol),request_path=str((rd/'request.preview.json').relative_to(ROOT)),
                before_candidate_sha256=before.get('candidate_sha256'),after_candidate_sha256=after.get('candidate_sha256'),
                final_candidate_sha256=row['frozen_sha256']))
    return dict(eligible=True,bridges=bridges,acquired_evidence_ids=len(sources),actually_visible_evidence_ids=len(visible_all),
        acquired_and_visible_evidence_ids=len(visible_acquired),query_submissions=len(acquisitions),
        physical_acquisition_executions=sum(a.get('cost',{}).get('native_execution_attempts',0) for a in acquisitions),
        acquisition_native_jobs_reused=sum(a.get('cost',{}).get('reused_native_execution_attempts',0) for a in acquisitions),
        source_file_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in bound_paths},
        warning='These are exact provenance and observed before/after links, not proof that a waveform alone caused an edit or held-out gain.')


def build(campaign,out):
    campaign=Path(campaign).resolve();out=Path(out).resolve();independent=campaign/'independent'
    complete=read(independent/'outcome.json',{}).get('status')=='completed'
    if not complete:
        status=dict(status='awaiting_completed_common_independent_acceptance',independent_grades_read=False,model_calls=0,native_executions=0,
            campaign_interruption=read(campaign/'interruption.json'),source=str(campaign))
        if read(out/'status.json')!=status:dump(out/'status.json',status)
        return status
    grades=read(independent/'results.json',[]);plan=read(independent/'plan.json',{})
    grade_keys=[(norm(g.get('folder',g.get('id'))),g['fault']) for g in grades]
    if len(grade_keys)!=len(set(grade_keys)):raise ValueError('duplicate_independent_version_fault_grade')
    parents_by_case={g['case_id']:g['parent_bug'] for g in grades}
    assigned_rows=report.trajectories(campaign/'base')
    assigned_qualification=[dict(case_id=r['case_id'],seed=r['seed'],search_strategy=r.get('search_strategy'),refinement_strategy=r['strategy'],
        folder=r['folder'],qualification=cards.trajectory_eligibility(r)) for r in assigned_rows]
    rows=[r for r in assigned_rows if r.get('strategy')=='R1' and r.get('search_strategy') in STRATEGIES]
    indexed={}
    for row in rows:
        key=(row['case_id'],row['seed'],row['search_strategy'])
        if key in indexed:raise ValueError('duplicate_R1_trajectory:'+str(key))
        indexed[key]=row
    bindings={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(cards.__file__),independent/'results.json',independent/'outcome.json',independent/'plan.json']}
    fine_fp_source=Path(__file__).with_name('research194_refinement_independent_pairs.py')
    bindings[str(fine_fp_source.relative_to(ROOT))]=hashlib.sha256(fine_fp_source.read_bytes()).hexdigest()
    if (campaign/'frozen_versions.json').exists():bindings[str((campaign/'frozen_versions.json').relative_to(ROOT))]=hashlib.sha256((campaign/'frozen_versions.json').read_bytes()).hexdigest()
    target_info={}
    # Read completed projections only for target-obligation links, never query
    # generation or test execution. One version has the same oracle population.
    for case_id,case_plan in plan.items():
        for fault in case_plan['faults']:
            p=independent/case_id/fault/'projection0.json'
            if not p.exists():continue
            measurement=read(p)
            for ev in measurement['evidence']:
                if ev.get('status')=='confirmed' and ev.get('counted_target'):
                    target_info[ev['evidence_id']]=dict(obligation=ev['obligation'],parent_bug=ev['parent_bug'],transaction_id=ev['transaction_id'],fault=fault)
    cells=[];pairs=[];bridge_rows=[]
    for case_id,seed in itertools.product(CASES,SEEDS):
        rr={s:indexed.get((case_id,seed,s)) for s in STRATEGIES}
        qualification={s:cards.trajectory_eligibility(r) if r else dict(eligible=False,reasons=['missing_frozen_trajectory']) for s,r in rr.items()}
        known=[r for r in rr.values() if r]
        same_initial=len({r.get('initial_sha256') for r in known})==1 and len(known)==4 and all(r.get('initial_sha256') for r in known)
        configurations={json.dumps(q.get('request_configuration'),sort_keys=True) for q in qualification.values()}
        same_configuration=len(configurations)==1 and None not in [q.get('request_configuration') for q in qualification.values()]
        trajectory_eligible=same_initial and same_configuration and all(q['eligible'] for q in qualification.values())
        per_strategy={s:{g['fault']:g for g in grades if r and cards.same_folder(g.get('folder'),r['folder'])} for s,r in rr.items()}
        expected=set(plan.get(case_id,{}).get('faults',[]));faults=[];eligible_faults=[]
        for fault in sorted(expected | set().union(*(set(v) for v in per_strategy.values()))):
            found={s:g[fault] for s,g in per_strategy.items() if fault in g};q=qualify_common_fault(found)
            faults.append(dict(fault=fault,**q))
            if q['eligible']:eligible_faults.append(fault)
        complete_fault_populations=bool(expected) and all(set(v)==expected for v in per_strategy.values())
        eligible=trajectory_eligible and complete_fault_populations and bool(eligible_faults)
        itt_eligible=same_initial and same_configuration and all(q.get('itt_frozen_assignment_eligible') for q in qualification.values()) and complete_fault_populations and bool(eligible_faults)
        scores={};bridges={};parent=parents_by_case.get(case_id,case_id)
        for strategy,row in rr.items():
            selected=[per_strategy[strategy][f] for f in eligible_faults]
            targets=set().union(*(set(g['target_ids']) for g in selected))
            timely=set().union(*(set(g['detected_ids']) for g in selected))
            detected=set().union(*(set(g['transaction_detected_ids']) for g in selected))
            bridge=evidence_bridges(row) if row else dict(eligible=False,bridges=[],reason='missing_frozen_trajectory')
            bridges[strategy]=bridge
            bridge_rows.append(dict(case_id=case_id,parent_bug=parent,seed=seed,search_strategy=strategy,folder=row['folder'] if row else None,**bridge))
            all_grades=list(per_strategy[strategy].values())
            fp_binding=cards.independent_fp_binding(independent,row,selected) if row and selected else dict(eligible=False,fp_units=[],reasons=['missing_common_grade_or_version'])
            scores[strategy]=dict(target_ids=sorted(targets),timely_detected_ids=sorted(timely),transaction_detected_ids=sorted(detected),
                late_detected_ids=sorted(detected-timely),transaction_missed_ids=sorted(targets-detected),
                timely_detection_rate=len(timely)/len(targets) if targets else None,
                transaction_detection_rate=len(detected)/len(targets) if targets else None,
                legal_fp_records_common=sum(g.get('false_positive_records',0) for g in selected),
                legal_fp_binding_common=fp_binding,
                legal_fp_records_all_observed=sum(g.get('false_positive_records',0) for g in all_grades),
                unknown_fault_rows=sum(bool(g.get('unknown_records')) for g in all_grades),
                unknown_records=sum(g.get('unknown_records',0) for g in all_grades),
                no_exposure_query_records=sum(len(g.get('no_exposure_queries',[])) for g in all_grades),
                model_calls=row.get('actual_model_calls',row.get('model_calls',0)) if row else 0,
                tokens_known=row.get('model_tokens_known',0) if row else 0,
                unknown_token_calls=row.get('model_token_unknown_calls',0) if row else 0,
                accepted_rounds=row.get('accepted_rounds',0) if row else 0,
                native_compiles=row.get('native_compile_attempts',0) if row else 0)
        cells.append(dict(case_id=case_id,parent_bug=parent,seed=seed,eligible=eligible,itt_eligible=bool(itt_eligible),trajectory_qualification=qualification,
            same_initial=same_initial,same_model_configuration=same_configuration,complete_fault_populations=complete_fault_populations,
            common_fault_qualification=faults,common_eligible_faults=eligible_faults,
            full_planned_scope_comparable=eligible and len(eligible_faults)==len(expected),scores=scores))
        for baseline,method in itertools.combinations(STRATEGIES,2):
            a,b=scores[method],scores[baseline];gained=set(a['transaction_detected_ids'])-set(b['transaction_detected_ids']);lost=set(b['transaction_detected_ids'])-set(a['transaction_detected_ids'])
            gain_obligations={target_info[x]['obligation'] for x in gained if x in target_info}
            matching_bridges=[x for x in bridges[method]['bridges'] if x['obligation'] in gain_obligations and x['newly_acquired_nonpublic_evidence']]
            fp_a=a['legal_fp_binding_common'];fp_b=b['legal_fp_binding_common']
            fp_change=cards.fp_context_comparison(fp_a,fp_b)
            no_new_fp=fp_change['no_new_fp']
            pairs.append(dict(case_id=case_id,parent_bug=parent,seed=seed,method=method,comparator=baseline,eligible=eligible,
                itt_eligible=bool(itt_eligible),
                common_faults=eligible_faults,target_count=len(a['target_ids']),gained_ids=sorted(gained),lost_ids=sorted(lost),
                full_planned_scope_comparable=eligible and len(eligible_faults)==len(expected),
                timely_gained_ids=sorted(set(a['timely_detected_ids'])-set(b['timely_detected_ids'])),
                timely_lost_ids=sorted(set(b['timely_detected_ids'])-set(a['timely_detected_ids'])),
                transaction_rate_delta=a['transaction_detection_rate']-b['transaction_detection_rate'] if eligible else None,
                timely_rate_delta=a['timely_detection_rate']-b['timely_detection_rate'] if eligible else None,
                itt_transaction_rate_delta=a['transaction_detection_rate']-b['transaction_detection_rate'] if itt_eligible else None,
                itt_timely_rate_delta=a['timely_detection_rate']-b['timely_detection_rate'] if itt_eligible else None,
                legal_fp_record_delta=a['legal_fp_records_common']-b['legal_fp_records_common'],
                new_legal_fp_units_common=fp_change['added_units'],
                legal_fp_context_bindings_complete=fp_change['bindings_complete'],
                model_call_delta=a['model_calls']-b['model_calls'],known_token_delta=a['tokens_known']-b['tokens_known'],
                no_loss_no_new_fp_gain=eligible and bool(gained) and not lost and no_new_fp,
                itt_no_loss_no_new_fp_gain=bool(itt_eligible) and bool(gained) and not lost and no_new_fp,
                same_obligation_new_evidence_edit_final_bridges=matching_bridges,
                attribution='Same-obligation provenance alignment is not proof that a particular development waveform caused a particular independent gain.'))
    parent_summary=[]
    for baseline,method in itertools.combinations(STRATEGIES,2):
        for parent in sorted({c['parent_bug'] for c in cells}):
            expected=[p for p in pairs if p['parent_bug']==parent and p['method']==method and p['comparator']==baseline]
            valid=[p for p in expected if p['eligible']]
            parent_summary.append(dict(parent_bug=parent,method=method,comparator=baseline,expected_seed_pairs=len(expected),eligible_seed_pairs=len(valid),
                fully_paired=len(valid)==len(expected)==2,
                fully_planned_scope_seed_pairs=sum(p['full_planned_scope_comparable'] for p in valid),
                common_fault_scope_by_seed={p['seed']:p['common_faults'] for p in valid},
                mean_transaction_rate_delta=statistics.mean(p['transaction_rate_delta'] for p in valid) if valid else None,
                mean_timely_rate_delta=statistics.mean(p['timely_rate_delta'] for p in valid) if valid else None,
                seed_pairs_with_no_loss_gain=sum(p['no_loss_no_new_fp_gain'] for p in valid),
                seed_pairs_with_lost_detection=sum(bool(p['lost_ids']) for p in valid),
                seed_pairs_with_new_legal_fp=sum(bool(p.get('new_legal_fp_units_common')) for p in valid),
                seed_pairs_with_new_evidence_bridge=sum(bool(p['same_obligation_new_evidence_edit_final_bridges']) for p in valid)))
    population=[]
    for baseline,method in itertools.combinations(STRATEGIES,2):
        parents=[p for p in parent_summary if p['method']==method and p['comparator']==baseline];balanced=[p for p in parents if p['fully_paired']]
        population.append(dict(method=method,comparator=baseline,expected_parents=len(parents),fully_paired_parents=len(balanced),
            partially_observed_or_excluded_parents=[p['parent_bug'] for p in parents if not p['fully_paired']],
            parent_macro_transaction_rate_delta=statistics.mean(p['mean_transaction_rate_delta'] for p in balanced) if balanced else None,
            parent_macro_timely_rate_delta=statistics.mean(p['mean_timely_rate_delta'] for p in balanced) if balanced else None,
            independent_parent_count_note='Two seeds remain paired repetitions of one parent Bug; transaction cycles never increase the parent count.'))
    result=dict(status='completed',search_R1_trajectories=len(rows),expected_search_R1_trajectories=32,case_seed_cells=len(cells),
        intention_to_treat=summarize_itt(pairs),itt_common_exposed_scope_case_seed_cells=sum(c['itt_eligible'] for c in cells),
        common_exposed_scope_comparable_case_seed_cells=sum(c['eligible'] for c in cells),
        fully_planned_scope_known_case_seed_cells=sum(c['full_planned_scope_comparable'] for c in cells),population=population,parent_summary=parent_summary,
        unknown_or_incomplete_units=[dict(case_id=c['case_id'],seed=c['seed'],trajectory_qualification=c['trajectory_qualification'],faults=c['common_fault_qualification']) for c in cells if not c['eligible']],
        excluded_fault_scope=[dict(case_id=c['case_id'],seed=c['seed'],faults=[f for f in c['common_fault_qualification'] if not f['eligible']]) for c in cells if any(not f['eligible'] for f in c['common_fault_qualification'])],
        model_calls=0,native_executions=0,independent_execution_performed=False,source_bindings=bindings,
        limitations=['Posthoc descriptive paired analysis; no dataset, candidate, algorithm or budget was changed.',
            'Intention-to-treat and strict normal-completion summaries are separate. A budget output truncation is a model outcome, not an infrastructure failure, and its retained frozen version remains in intention-to-treat.',
            'Both paired summaries use the common four-strategy eligible fault/target intersection. All unknown, unexposed and excluded units remain listed.',
            'Parent macro comparison requires both predeclared seeds for that parent; partial parents are shown separately, never filled as passes.',
            'Late alarms on matching confirmed violation cycles count as transaction detection but not first-violation detection.',
            'No-new-FP gain flags require set inclusion of candidate-bound legal alarm contexts (fault, query, variant, cycle, obligation), ignoring labels. FP record-count deltas remain descriptive and do not authorize those flags.',
            'Search evidence, accepted edit and retained final detection are linked exactly. Same-obligation held-out gain is an association, not single-waveform causation.',
            'Three cases use artificial obligation faults on real project RTL. Ibex covers the recorded historical flush sub-fix, not a full CPU verification claim.'])
    dump(out/'paired_outcomes.json',pairs);dump(out/'case_seed_cells.json',cells);dump(out/'evidence_edit_final_links.json',bridge_rows)
    dump(out/'all_assigned_trajectory_qualification.json',assigned_qualification)
    dump(out/'analysis.json',result);dump(out/'status.json',dict(status='completed',independent_grades_read=True,model_calls=0,native_executions=0))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--campaign',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--wait',action='store_true')
    args=ap.parse_args()
    while True:
        result=build(args.campaign,args.out)
        if result['status']=='completed' or not args.wait or result.get('campaign_interruption'):break
        time.sleep(5)
    print(json.dumps(dict(status=result['status'],model_calls=0,native_executions=0)))


if __name__=='__main__':main()
