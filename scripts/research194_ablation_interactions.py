"""Read-only factorial contrasts after the complete frozen independent run."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

import research194_report as report
import research194_case_cards as cards

ROOT = Path(__file__).resolve().parents[1]
ARMS = {'A0': ('S0', 'R1'), 'A1': ('S3', 'R1'),
        'A2': ('S0', 'R3'), 'A3': ('S3', 'R3')}


def contrasts(values):
    return dict(active_without_local=values['A1']-values['A0'],
                active_with_local=values['A3']-values['A2'],
                local_without_active=values['A2']-values['A0'],
                local_with_active=values['A3']-values['A1'],
                interaction=values['A3']-values['A2']-values['A1']+values['A0'])


def build(campaign, out):
    campaign, out = Path(campaign).resolve(), Path(out).resolve()
    independent = campaign/'independent'
    if report.read(independent/'outcome.json', {}).get('status') != 'completed':
        raise ValueError('independent_run_not_completed_no_test_reads')
    grades = report.read(independent/'results.json', [])
    plan = report.read(independent/'plan.json', {})
    trajectories = report.trajectories(campaign/'base')
    by_key = {(r['case_id'], r['seed'], r['search_strategy'], r['strategy']): r
              for r in trajectories}
    if len(by_key) != len(trajectories):raise ValueError('duplicate_trajectory_assignment')
    grade_keys=[(str(g.get('folder',g.get('id'))).replace('\\','/'),g['fault']) for g in grades]
    if len(grade_keys)!=len(set(grade_keys)):raise ValueError('duplicate_version_fault_grade')
    cells = []
    for case in ('arbiter', 'counter', 'uart', 'ibex_flush'):
        for seed in (19407, 19419):
            runs = {a: by_key[(case, seed, *method)] for a, method in ARMS.items()}
            qualification = {a: cards.trajectory_eligibility(r) for a, r in runs.items()}
            sets = {a: {g['fault']: g for g in grades if cards.same_folder(g.get('folder'),r['folder'])}
                    for a, r in runs.items()}
            shared_initial = all(r.get('initial_sha256') for r in runs.values()) and len({r['initial_sha256'] for r in runs.values()}) == 1
            shared_model = all(q.get('request_configuration') for q in qualification.values()) and len({json.dumps(q['request_configuration'],sort_keys=True) for q in qualification.values()})==1
            shared_parent=len({r['parent_bug'] for r in runs.values()})==1
            expected=set(plan.get(case,{}).get('faults',[]))
            complete_population=bool(expected) and all(set(x)==expected for x in sets.values())
            faults = sorted(expected | set.union(*(set(x) for x in sets.values())))
            fault_rows = []
            for fault in faults:
                gg = {a: x[fault] for a, x in sets.items() if fault in x}
                reasons = []
                if len(gg) != 4: reasons.append('missing_arm')
                if any(not g['native_complete'] or not g['reference_complete'] for g in gg.values()):
                    reasons.append('incomplete_native_or_reference')
                if any(g['unknown_records'] for g in gg.values()): reasons.append('unknown')
                if any(not g['valid_reachable_fault'] or not g['target_ids'] for g in gg.values()):
                    reasons.append('invalid_or_unexposed')
                if len({tuple(sorted(g['target_ids'])) for g in gg.values()}) != 1:
                    reasons.append('unequal_target_population')
                if len({tuple(sorted(g.get('necessary_obligations',[]))) for g in gg.values()})!=1:
                    reasons.append('unequal_necessary_obligations')
                row = dict(fault=fault, eligible=not reasons, reasons=reasons,
                           unknown_queries={a:g['unknown_queries'] for a,g in gg.items()},
                           unexposed_queries={a:g['no_exposure_queries'] for a,g in gg.items()})
                if not reasons:
                    row['arm_metrics'] = {a:dict(transaction_rate=g['transaction_detected']/len(g['target_ids']),
                        timely_rate=g['detected']/len(g['target_ids']), fp_records=g['false_positive_records'],
                        necessary_obligation_protection=g['necessary_obligation_transaction_protection_rate'])
                        for a,g in gg.items()}
                    row['contrasts'] = {m:contrasts({a:row['arm_metrics'][a][m] for a in ARMS})
                        for m in ('transaction_rate','timely_rate','fp_records','necessary_obligation_protection')}
                fault_rows.append(row)
            valid = [f for f in fault_rows if f['eligible']]
            itt = bool(shared_initial and shared_model and shared_parent and complete_population and all(q['itt_frozen_assignment_eligible'] for q in qualification.values()) and valid)
            cell = dict(case_id=case,parent_bug=runs['A0']['parent_bug'],seed=seed,
                        itt_eligible=itt,strict_eligible=itt and all(q['eligible'] for q in qualification.values()),
                        same_initial=bool(shared_initial),same_model_configuration=bool(shared_model),same_parent=shared_parent,
                        expected_faults=sorted(expected),complete_fault_populations=complete_population,
                        observed_faults_by_arm={a:sorted(x) for a,x in sets.items()},
                        trajectory_qualification=qualification,faults=fault_rows,
                        all_observed_unknown_records={a:sum(g['unknown_records'] for g in x.values()) for a,x in sets.items()},
                        all_observed_legal_fp_records={a:sum(g['false_positive_records'] for g in x.values()) for a,x in sets.items()},
                        full_fault_population_known=complete_population and len(valid)==len(expected),
                        all_planned_queries_exposed=complete_population and len(valid)==len(expected) and all(not g.get('no_exposure_queries') for x in sets.values() for g in x.values()))
            if itt:
                cell['mean_contrasts'] = {m:{k:statistics.mean(f['contrasts'][m][k] for f in valid)
                    for k in valid[0]['contrasts'][m]} for m in valid[0]['contrasts']}
            cells.append(cell)
    summaries = {}
    for view, flag in (('intention_to_treat','itt_eligible'),('strict_completed','strict_eligible')):
        parents = []
        for parent in sorted({c['parent_bug'] for c in cells}):
            selected = [c for c in cells if c['parent_bug']==parent and c[flag]]
            row = dict(parent_bug=parent,eligible_seed_cells=len(selected),fully_paired=len(selected)==2)
            if len(selected)==2:
                row['mean_contrasts'] = {m:{k:statistics.mean(c['mean_contrasts'][m][k] for c in selected)
                    for k in selected[0]['mean_contrasts'][m]} for m in selected[0]['mean_contrasts']}
            parents.append(row)
        balanced=[p for p in parents if p['fully_paired']]
        summaries[view]=dict(parents=parents,fully_paired_parents=len(balanced),
            parent_macro_contrasts={m:{k:statistics.mean(p['mean_contrasts'][m][k] for p in balanced)
                for k in balanced[0]['mean_contrasts'][m]} for m in balanced[0]['mean_contrasts']} if balanced else None)
    sources=[Path(__file__),Path(cards.__file__),independent/'results.json',independent/'outcome.json',independent/'plan.json']
    sources += [p for p in (campaign/'protocol.json',campaign/'frozen_versions.json') if p.exists()]
    result=dict(cells=cells,summaries=summaries,model_calls=0,native_executions=0,
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        interaction_definition='A3 - A2 - A1 + A0; positive detection interaction is additional descriptive gain, not statistical proof.',
        aggregation='Equal eligible fault weights within case/seed, then seeds within parent, then fully paired parents. Unknown faults excluded explicitly; no-exposure queries remain listed and never become passes.',
        scope='Initial candidate and observed model configuration must match all four arms; frozen plan fault sets must be complete. ITT retains budget truncation; strict excludes abnormal completion. Full known fault population does not mean every planned query exposed a fault. Four parents and shared stimuli across seeds do not support broad significance claims.')
    report.dump(out/'analysis.json',result)
    print(json.dumps({k:v['fully_paired_parents'] for k,v in summaries.items()}))
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--campaign',type=Path,default=ROOT/'deliverables/research194_campaign_execute_20261103_r01')
    p.add_argument('--out',type=Path,default=ROOT/'deliverables/research194_ablation_interactions_20261103_r01')
    build(**vars(p.parse_args()))
