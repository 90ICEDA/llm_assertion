"""Read-only R195 outcomes, cost, paired acceptance and provenance normalization.

No model/native execution and no mutation of sealed or archived evidence.
Independent results are never opened before their completed marker.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import html
import json
from pathlib import Path
import re
import time
from research194_refinement_fp_audit import compare as audit_legal_history


def read(path,default=None):
    path=Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def token_sections(rows,grade_index):
    """Posthoc indivisible completed-call prefixes using existing projections."""
    details=[]
    for fixture,seed in sorted({(r['fixture'],r['seed']) for r in rows}):
        cohort=[r for r in rows if (r['fixture'],r['seed'])==(fixture,seed)]
        common_support=len(cohort)==3 and all(r['model_calls']==1 and r['usage_complete'] for r in cohort)
        cuts=[('fixed',cut) for cut in (0,16384,32768,65536)]
        cuts.append(('minimum_actual_total',min(r['tokens_known'] for r in cohort)))
        for kind,cut in cuts:
            for row in cohort:
                included=row['model_calls']==1 and row['usage_complete'] and row['tokens_known']<=cut
                grade=grade_index[row['id'] if included else fixture+'/initial_control']
                projection=read(Path(grade['projection']))
                initial=read(Path(grade_index[fixture+'/initial_control']['projection']))
                comparison=independent_pair(projection,initial)
                activity=row.get('independent_component_activity' if included else 'independent_initial_component_activity',{})
                component_triggers={label:dict(trigger_samples=value['trigger_samples'],finite_untriggered=value['finite_untriggered'],
                    own_triggered_targets=len(value['own_triggered_target_ids']),own_detected_targets=len(value['own_any_cycle_detected_ids']))
                    for label,value in activity.get('assertions',{}).items()}
                details.append(dict(id=row['id'],fixture=fixture,seed=seed,arm=row['arm'],cut_kind=kind,token_cut=cut,
                    three_arm_known_actual_call_support=common_support,completed_call_in_prefix=included,
                    completed_prefix_tokens=row['tokens_known'] if included else 0,
                    full_experiment_actual_tokens=row['tokens_known'],full_experiment_classification=row['classification'],
                    selected_state='retained_terminal' if included else 'initial',
                    selected_candidate_origin='accepted_model' if included and row['gate_accepted'] else 'initial',
                    selected_independent_component_triggers=component_triggers,
                    accepted_update_in_prefix=included and row['gate_accepted'],
                    semantic_repair_qualified=included and row['semantic_repair_qualified'] is True,
                    selected_candidate_sha256=grade['candidate_sha256'],projection=grade['projection'],
                    targets=len(grade['targets']),timely_detected_targets=len(grade['timely_detected_ids']),
                    any_cycle_detected_targets=len(grade['transaction_detected_ids']),
                    legal_alarm_units=len(fine_alarms(projection)),unknown=len(grade['critical_unknown']),
                    independent_vs_initial=comparison))
    summary=[]
    for kind,cut in [('fixed',cut) for cut in (0,16384,32768,65536)]+[('minimum_actual_total',None)]:
        for arm in ('F','P','L'):
            chosen=[d for d in details if d['cut_kind']==kind and d['arm']==arm and (cut is None or d['token_cut']==cut)]
            eligible=[d for d in chosen if d['three_arm_known_actual_call_support'] and d['independent_vs_initial']['eligible']]
            summary.append(dict(cut_kind=kind,token_cut=cut,arm=arm,population=len(chosen),
                completed_calls=sum(d['completed_call_in_prefix'] for d in chosen),
                completed_prefix_tokens=sum(d['completed_prefix_tokens'] for d in chosen),
                accepted_updates=sum(d['accepted_update_in_prefix'] for d in chosen),
                nonvacuous_improvements=sum(d['semantic_repair_qualified'] for d in chosen),
                eligible_common_support=len(eligible),
                eligible_pair_repeated_removed_legal_alarm_units=sum(len(d['independent_vs_initial']['legal_alarm']['removed']) for d in eligible),
                eligible_pair_repeated_gained_targets=sum(len(d['independent_vs_initial']['any_cycle']['gained']) for d in eligible),
                eligible_pair_repeated_lost_targets=sum(len(d['independent_vs_initial']['any_cycle']['lost']) for d in eligible)))
    return dict(provenance='posthoc_read_only_completed_prefix',new_model_calls=0,new_native_jobs=0,details=details,summary=summary,
        interpretation=[
            'A single call is indivisible. Above-cut calls retain the already measured initial control, with zero completed-prefix cost; their full actually incurred cost remains recorded separately.',
            'Truncated, rejected and unchanged calls consume their full measured tokens when inside the cut, while retaining initial assertions. No failure cost is erased.',
            'The three-arm minimum may complete only the cheapest arm. Equal token ceilings do not imply equal consumed tokens or partial-call outputs.',
            'Delay blocked arms remain in the population but lack three actual calls and are excluded from common-support comparisons.',
            'Eligible aggregate target/alarm sums repeat seeds and are paired descriptive units, not independent fault discoveries.'])


def classify(mode,outcome,rounds,model,proposal):
    last=rounds[-1] if rounds else {};status=last.get('status');decision=last.get('decision',{})
    if mode=='blocked_unknown':return 'not_attempted_initial_unknown'
    if not outcome and not model:return 'pending_not_attempted'
    if not outcome:return 'in_progress'
    if model.get('status')=='response_truncated' or model.get('done_reason')=='length':return 'model_failure_output_budget'
    if status=='model_transport_or_decode_failure':return 'model_failure_transport_or_decode'
    if status=='interface_rejected':return 'interface_failure'
    if status=='infrastructure_interrupted' or (proposal and proposal.get('native_complete') is not True):return 'native_execution_failure'
    if decision.get('critical_unknown') or status=='unknown_acquisition_or_history':return 'native_or_reference_unknown'
    if status=='no_change':return 'no_change'
    if status=='accepted':return 'gate_accepted'
    if status=='rejected':return 'no_retained_benefit_native_rejected'
    if outcome.get('termination_reason'):return 'outer_execution_failure'
    return 'unresolved_execution_state'


def fine_alarms(measurement):
    return {(e.get('query_id'),e.get('variant'),e.get('cycle'),e.get('obligation'))
        for e in measurement.get('evidence',[]) if e.get('variant')=='correct'
        and e.get('status')=='confirmed' and e.get('label')=='legal'
        and any(a.get('failure') for a in e.get('assertions',[]))}


def native_activity(measurement,candidate,label_map=None):
    """Count actual native antecedent markers, not aggregate target triggering."""
    names={a['label'] for a in candidate};hits={name:set() for name in names};complete=True
    jobs=measurement.get('executions',[])
    for job in jobs:
        result=job.get('result',{})
        complete=complete and result.get('compile_status')=='passed' and result.get('execution_status')=='completed'
        for marker in result.get('triggers',[]):
            label=marker.get('id');label=(label_map or {}).get(label,label)
            cycle=re.search(r'cycle=(\d+)',marker.get('detail',''))
            if label in hits and cycle:hits[label].add((job.get('query_id'),job.get('variant'),int(cycle[1])))
    targets={(e.get('transaction_id'),e.get('obligation')):e['id'] for e in measurement.get('evidence',[])
        if e.get('status')=='confirmed' and e.get('label')=='violation' and e.get('counted_target',True)}
    details={}
    for assertion in candidate:
        name=assertion['label'];triggered=set();timely=set();any_cycle=set();legal=set()
        required={eid for (_,ob),eid in targets.items() if ob in assertion['obligations']}
        for ev in measurement.get('evidence',[]):
            observations=[a for a in ev.get('assertions',[]) if a.get('assertion')==name]
            if ev.get('status')!='confirmed':continue
            if ev.get('label')=='violation':
                target=targets.get((ev.get('transaction_id'),ev.get('obligation')))
                if target and any(a.get('failure') for a in observations):any_cycle.add(target)
                if ev.get('counted_target',True):
                    if any(a.get('trigger') for a in observations):triggered.add(ev['id'])
                    if any(a.get('failure') for a in observations):timely.add(ev['id'])
            if ev.get('label')=='legal' and ev.get('variant')=='correct' and any(a.get('failure') for a in observations):
                legal.add((ev.get('query_id'),'correct',ev.get('cycle'),ev.get('obligation')))
        details[name]=dict(trigger_samples=len(hits[name]),finite_untriggered=bool(jobs) and complete and not hits[name],
            associated_required_targets=sorted(required),own_triggered_target_ids=sorted(triggered),
            own_timely_detected_ids=sorted(timely),own_any_cycle_detected_ids=sorted(any_cycle),legal_alarm_units=sorted(legal,key=str))
    return dict(native_complete=bool(jobs) and complete,assertions=details)


def independent_pair(a,b):
    ta=set(a['targets']);tb=set(b['targets']);common=ta&tb
    reasons=[]
    if ta!=tb:reasons.append('target_population_mismatch')
    if not common:reasons.append('no_common_confirmed_target')
    if any(m.get('native_complete') is not True or m.get('reference_complete') is not True or m.get('critical_unknown') for m in (a,b)):
        reasons.append('unknown_or_incomplete_acceptance')
    result=dict(eligible=not reasons,exclusion_reasons=reasons,common_targets=len(common),
        left_only_targets=sorted(ta-tb),right_only_targets=sorted(tb-ta))
    for label,key in [('timely','detected_ids'),('any_cycle','transaction_detected_ids')]:
        da=set(a[key])&common;db=set(b[key])&common
        result[label]=dict(gained=sorted(da-db),lost=sorted(db-da),both_missed=sorted(common-da-db),left_detected=len(da),right_detected=len(db))
    fa=fine_alarms(a);fb=fine_alarms(b)
    result['legal_alarm']=dict(added=sorted(fa-fb,key=str),removed=sorted(fb-fa,key=str),left=len(fa),right=len(fb))
    return result


def analyze(prepared,execution,independent,out,replay):
    prepared=Path(prepared);execution=Path(execution);independent=Path(independent);out=Path(out)
    protocol=read(prepared/'protocol.json');seal=read(prepared/'seal.json');ledger=read(execution/'ledger.json',[])
    # Guard before any independent index or projection access.
    acceptance_completed=read(independent/'outcome.json',{}).get('status')=='completed'
    grades=read(independent/'results.json',[]) if acceptance_completed else []
    grade_index={g['id']:g for g in grades};rows=[];history_audits=[];calls=[];contract=[]
    for entry in protocol['entries']:
        folder=execution/entry['id']/'refinement';outcome=read(folder/'outcome.json',{})
        rounds=read(folder/'rounds.json',[]);last=rounds[-1] if rounds else {};rd=folder/'round01'
        model=read(rd/'model_call/result.json',{})
        proposal=read(rd/'proposal_native/measurement.json',{})
        before=read(rd/'current_measurement.json',{})
        initial=read(folder/'initial.json',read(Path(entry['state']),{}).get('initial',[]))
        proposed_candidate=read(rd/'proposal.json',[])
        before_activity=native_activity(before,initial) if before else {}
        after_activity=native_activity(proposal,proposed_candidate) if proposal else {}
        newly_inactive=[label for label,activity in after_activity.get('assertions',{}).items()
            if activity['finite_untriggered'] and before_activity.get('assertions',{}).get(label,{}).get('trigger_samples',0)>0]
        raw_edit=read(rd/'model_edit.json',{})
        operators=[e.get('op') for e in raw_edit.get('edits',[]) if isinstance(e,dict)] if isinstance(raw_edit,dict) else []
        decision=last.get('decision',{});status=classify(entry['mode'],outcome,rounds,model,proposal)
        call_cost=dict(model_calls=model.get('model_calls',0),prompt_tokens=model.get('prompt_tokens'),completion_tokens=model.get('completion_tokens'),
            tokens_known=(model.get('prompt_tokens') or 0)+(model.get('completion_tokens') or 0),
            usage_complete=bool(model) and model.get('prompt_tokens') is not None and model.get('completion_tokens') is not None)
        if model:calls.append(dict(id=entry['id'],record=str(rd/'model_call/result.json'),status=model.get('status'),**call_cost))
        if model:
            actual_request=read(rd/'model_call/request.json',{})
            attempt=read(rd/'model_call/attempt.json',{})
            reserved=next((c for c in ledger if c.get('id')==entry['id']),{})
            contract.append(dict(id=entry['id'],sealed_payload_identical=actual_request==read(entry['request']),
                ledger_payload_hash_matches=digest(actual_request)==reserved.get('request_sha256')==entry['request_sha256'],
                endpoint_matches=model.get('endpoint')==protocol['endpoint'],requested_model_matches=actual_request.get('model')==protocol['model'],
                reported_model=model.get('actual_server_model'),provider_response_id=model.get('response_id'),
                model_reported_matches=model.get('actual_server_model')==protocol['model'],
                timeout_matches=attempt.get('timeout_seconds')==300,zero_retries=attempt.get('retries')==0 and model.get('retries')==0,
                output_budget_matches=actual_request.get('max_tokens')==2048,temperature_matches=actual_request.get('temperature')==.2,
                requested_seed_matches=actual_request.get('seed')==entry['seed']))
        if last.get('status')=='accepted' and before and proposal:
            history_audits.append(dict(id=entry['id'],**audit_legal_history(before,proposal,read(folder/'initial.json'),read(rd/'proposal.json'))))
        native_cost=read(folder/'cost_components.json',[])
        historical_loss=bool(decision.get('lost_ids') or decision.get('historical_any_cycle_lost_ids'))
        row=dict(id=entry['id'],fixture=entry['fixture'],case_id=entry['case_id'],seed=entry['seed'],arm=entry['arm'],
            mode=entry['mode'],classification=status,terminal=outcome.get('status')=='frozen',folder=str(folder),
            raw_outer_status=last.get('status'),raw_model_status=model.get('status'),raw_outcome_classification=outcome.get('classification'),
            frozen_sha256=outcome.get('frozen_sha256'),**call_cost,
            actual_submitted_attempt=(rd/'model_call/attempt.json').exists(),
            model_edit_operators=operators,before_component_activity=before_activity,after_component_activity=after_activity,
            newly_finite_untriggered_components=newly_inactive,
            accepted_component_inactivity=last.get('status')=='accepted' and bool(newly_inactive),
            native_compile_attempts=sum(c.get('native_compile_attempts',0) for c in native_cost),
            native_execution_attempts=sum(c.get('native_execution_attempts',0) for c in native_cost),
            native_seconds=sum(c.get('native_seconds',0) for c in native_cost),
            native_wall_seconds=sum(c.get('wall_seconds',0) for c in native_cost),
            shared_lock_wait_seconds=sum(c.get('shared_lock_wait_seconds',0) for c in native_cost),
            proposed_timely_gained=len(decision.get('timely_gained_ids',[])),proposed_any_cycle_gained=len(decision.get('transaction_gained_ids',[])),
            fixed_false_positive_ids=decision.get('fixed_false_positive_ids',[]),new_false_positive_ids=decision.get('new_false_positive_ids',[]),
            proposed_history_loss=historical_loss,historical_rejection=historical_loss and not decision.get('accepted',False),
            history_guard_decisive=historical_loss and not decision.get('accepted',False) and bool(decision.get('timely_gained_ids') or decision.get('transaction_gained_ids') or decision.get('fixed_false_positive_ids')) and not(decision.get('critical_unknown') or decision.get('new_false_positive_ids')),
            critical_unknown=decision.get('critical_unknown',[]),error=last.get('error',outcome.get('error')),
            independent_grade=grade_index.get(entry['id']))
        changed=[a['label'] for a in proposed_candidate if a!=next((b for b in initial if b['label']==a['label']),None)]
        row['changed_components']=changed
        row['gate_accepted']=last.get('status')=='accepted'
        row['semantic_repair_qualified']=None
        row['semantic_qualification_status']='pending_independent_acceptance'
        row['evidence_links']=dict(request=str(rd/'request.preview.json'),raw_model_edit=str(rd/'model_edit.json'),
            native_proposal_measurement=str(rd/'proposal_native/measurement.json'),
            native_logs=[str(Path(j['folder'])/'execute.log') for j in proposal.get('executions',[])],
            independent_projection=grade_index.get(entry['id'],{}).get('projection'))
        if acceptance_completed:
            grade=grade_index[entry['id']];control_grade=grade_index[entry['fixture']+'/initial_control']
            final_measurement=read(grade['projection']);control_measurement=read(control_grade['projection'])
            mapping=read(independent/entry['fixture']/'version_mapping.json')
            index=mapping['keys'].index(grade['candidate_sha256'])
            native_label_map={label:meta['original_label'] for label,meta in mapping['mapping'].items() if meta['candidate']==index}
            final_candidate=read(folder/'frozen.json')
            activity=native_activity(final_measurement,final_candidate,native_label_map)
            control_index=mapping['keys'].index(control_grade['candidate_sha256'])
            control_map={label:meta['original_label'] for label,meta in mapping['mapping'].items() if meta['candidate']==control_index}
            control_activity=native_activity(control_measurement,initial,control_map)
            comparison=independent_pair(final_measurement,control_measurement)
            target_to_transaction={e['id']:e['transaction_id'] for e in final_measurement.get('evidence',[])
                if e.get('status')=='confirmed' and e.get('label')=='violation' and e.get('counted_target',True)}
            row['independent_counting_units']=dict(confirmed_transaction_obligation_targets=len(final_measurement['targets']),
                unique_confirmed_transaction_ids=len(set(target_to_transaction.values())),
                timely_detected_transaction_obligation_targets=len(final_measurement['detected_ids']),
                any_cycle_detected_transaction_obligation_targets=len(final_measurement['transaction_detected_ids']),
                transactions_with_at_least_one_timely_detected_obligation=len({target_to_transaction[i] for i in final_measurement['detected_ids'] if i in target_to_transaction}),
                transactions_with_at_least_one_any_cycle_detected_obligation=len({target_to_transaction[i] for i in final_measurement['transaction_detected_ids'] if i in target_to_transaction}),
                warning='At least one detected obligation does not prove all obligations of that transaction are protected.')
            reasons=[]
            if not row['gate_accepted']:reasons.append('not_accepted_by_sealed_gate')
            if not comparison['eligible']:reasons.extend(comparison['exclusion_reasons'])
            if comparison['legal_alarm']['added']:reasons.append('new_independent_legal_alarm')
            if comparison['any_cycle']['lost'] or comparison['timely']['lost']:reasons.append('lost_independent_detection')
            if not changed:reasons.append('no_changed_component')
            component_gains=[]
            for label in changed:
                current_activity=activity['assertions'].get(label,{})
                old_activity=control_activity['assertions'].get(label,{})
                if current_activity.get('finite_untriggered'):reasons.append('changed_component_finitely_untriggered:'+label)
                old_alarm={tuple(x) for x in old_activity.get('legal_alarm_units',[])}
                new_alarm={tuple(x) for x in current_activity.get('legal_alarm_units',[])}
                detected_gain=set(current_activity.get('own_any_cycle_detected_ids',[]))-set(old_activity.get('own_any_cycle_detected_ids',[]))
                component_gains.append(dict(assertion=label,independent_legal_alarms_fixed=sorted(old_alarm-new_alarm,key=str),
                    independent_own_detection_gained=sorted(detected_gain)))
            if not any(g['independent_legal_alarms_fixed'] or g['independent_own_detection_gained'] for g in component_gains):
                reasons.append('no_independent_component_improvement')
            row.update(independent_component_activity=activity,independent_initial_component_activity=control_activity,
                independent_component_gains=component_gains,independent_vs_initial=comparison,
                semantic_repair_qualified=not reasons,semantic_qualification_reasons=reasons,
                semantic_qualification_status='posthoc_nonvacuous_improvement_on_executed_scope_not_formal_semantic_proof')
        rows.append(row)
    pairs=[];by_id={r['id']:r for r in rows}
    for fixture in sorted({e['fixture'] for e in protocol['entries']}):
        for seed in protocol['seeds']:
            for left,right in [('P','F'),('L','P'),('L','F')]:
                a=by_id[f'{fixture}/{seed}/{left}'];b=by_id[f'{fixture}/{seed}/{right}']
                pair=dict(fixture=fixture,case_id=a['case_id'],seed=seed,comparison=f'{left}_vs_{right}',
                    left_status=a['classification'],right_status=b['classification'],
                    left_tokens=a['tokens_known'],right_tokens=b['tokens_known'],token_difference=a['tokens_known']-b['tokens_known'],
                    both_actual_calls_and_known_usage=all(r['model_calls']==1 and r['usage_complete'] for r in (a,b)),
                    identical_model_call_ceiling=1,identical_max_output=2048,
                    both_accepted=all(r['classification']=='gate_accepted' for r in (a,b)),
                    interpretation={'P_vs_F':'Localization hint effect with the same free editing domain.',
                        'L_vs_P':'Constrained field-edit domain effect with the same localization hints.',
                        'L_vs_F':'Combined localization and constrained-edit policy difference.'}[f'{left}_vs_{right}'])
                if acceptance_completed:
                    ga=a['independent_grade'];gb=b['independent_grade']
                    ma=read(Path(ga['projection']));mb=read(Path(gb['projection']))
                    if ma['candidate_sha256']!=a['frozen_sha256'] or mb['candidate_sha256']!=b['frozen_sha256']:raise ValueError('frozen_independent_candidate_mismatch')
                    pair['independent']=independent_pair(ma,mb)
                    failures={'model_failure_output_budget','model_failure_transport_or_decode','native_execution_failure','native_or_reference_unknown','outer_execution_failure','not_attempted_initial_unknown'}
                    pair['sensitivity_eligible']=pair['independent']['eligible'] and pair['both_actual_calls_and_known_usage'] and not any(r['classification'] in failures for r in (a,b))
                    pair['known_token_cost_common_support']=pair['independent']['eligible'] and pair['both_actual_calls_and_known_usage']
                pairs.append(pair)
    aggregates=[]
    for fixture in sorted({r['fixture'] for r in rows}):
        for arm in ('F','P','L'):
            selected=[r for r in rows if (r['fixture'],r['arm'])==(fixture,arm)]
            aggregates.append(dict(fixture=fixture,arm=arm,population=len(selected),classifications=dict(Counter(r['classification'] for r in selected)),
                model_calls=sum(r['model_calls'] for r in selected),known_tokens=sum(r['tokens_known'] for r in selected),
                accepted=sum(r['classification']=='gate_accepted' for r in selected),
                semantic_repair_qualified=sum(r['semantic_repair_qualified'] is True for r in selected),
                accepted_component_inactivity=sum(r['accepted_component_inactivity'] for r in selected),
                native_proposals=sum(r['raw_outer_status'] in ('accepted','rejected') for r in selected),
                proposed_history_loss=sum(r['proposed_history_loss'] for r in selected),history_guard_decisive=sum(r['history_guard_decisive'] for r in selected)))
    replay_path=Path(replay);archived=read(replay_path/'outcome.json',{})
    normalization=dict(source=str(replay_path/'outcome.json'),provenance=archived.get('provenance'),
        original_causal_comparison_eligible=archived.get('causal_comparison_eligible'),normalized_causal_comparison_eligible=False,
        inherited_field_error=archived.get('causal_comparison_eligible') is True,
        reason='Archived response was generated for another request and has zero new model calls. The generic runner inherited true from execution completeness; that does not establish causal model-comparison eligibility.',
        source_unchanged=True,integration_qualification_only=True)
    qualification_costs=[]
    for path in sorted(Path(protocol['qualification']).glob('*/before/cost.json'))+sorted(Path(protocol['qualification']).glob('*/after/cost.json')):
        qualification_costs.append(dict(path=str(path),**read(path)))
    independent_costs=read(independent/'physical_cost.json',[]) if acceptance_completed else []
    def cost_sum(costs):
        return {key:sum(c.get(key,0) for c in costs) for key in ('native_compile_attempts','native_execution_attempts','native_seconds','wall_seconds','shared_lock_wait_seconds')}
    phase_costs=dict(handwritten_native_qualification=cost_sum(qualification_costs),
        independent_native_acceptance=cost_sum(independent_costs),
        archival_integration_r02=dict(native_compile_attempts=archived.get('native_compile_attempts'),native_execution_attempts=archived.get('native_execution_attempts'),new_model_calls=0),
        inclusion_rule='Qualification and archival integration are separate overhead, never charged as additional paired-model-arm discoveries or calls.')
    compat_folder=independent.parent/'research195_refinement_independent_compat_20261103_r01'
    incident=read(compat_folder/'original_incident.json',{})
    correction_path=compat_folder/'incident_correction.json'
    correction=json.loads(correction_path.read_text(encoding='utf-8-sig')) if correction_path.is_file() else {}
    if incident:
        phase_costs['independent_failed_r01_overhead']=dict(native_compile_attempts=incident['completed_compiles'],
            native_execution_attempts=incident['completed_executions'],native_seconds=incident['physical_seconds'],
            new_model_calls=0,classification='independent_query_metadata_interface_failure',
            original_incident_path=str(compat_folder/'original_incident.json'),corrected_attribution=correction)
        phase_costs['independent_compatibility']=read(compat_folder/'outcome.json',{})
    archive_r01=read(replay_path.parent/'research195_refinement_uart_replay_20261103_r01/outcome.json',{})
    if archive_r01:
        phase_costs['archival_integration_r01_overhead']=dict(native_compile_attempts=archive_r01.get('native_compile_attempts'),
            native_execution_attempts=archive_r01.get('native_execution_attempts'),new_model_calls=0,
            interpretation='Earlier archival integration qualification, outside the paired model experiment.')
    checks=[k for k in contract[0] if k.endswith('_matches') or k in ('sealed_payload_identical','zero_retries')] if contract else []
    source_checks={path:Path(path).is_file() and hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected for path,expected in protocol['source_bindings'].items()}
    contract_audit=dict(records=contract,physical_results=len(contract),ledger_reservations=len(ledger),maximum_calls=protocol['maximum_model_calls'],
        no_budget_excess=len(ledger)<=protocol['maximum_model_calls'],no_duplicate_payload_reservations=len({c['request_sha256'] for c in ledger})==len(ledger),
        all_recorded_contract_checks_pass=all(all(c[k] for k in checks) for c in contract),
        checks=checks,source_bindings_unchanged=all(source_checks.values()),source_binding_count=len(source_checks),
        changed_sources=[path for path,ok in source_checks.items() if not ok])
    summary=dict(status='independent_completed_read_only' if acceptance_completed else 'model_phase_complete' if all(r['terminal'] for r in rows) else 'execution_pending_or_running',
        timestamp_unix=time.time(),registered_population=len(rows),terminal_population=sum(r['terminal'] for r in rows),
        maximum_model_calls=protocol['maximum_model_calls'],ledger_reservations=len(ledger),
        actual_model_calls=sum(c['model_calls'] for c in calls),known_tokens=sum(c['tokens_known'] for c in calls),
        submitted_attempt_records=sum(r['actual_submitted_attempt'] for r in rows),
        completed_model_result_records=len(calls),
        unknown_usage_calls=sum(c['model_calls']>0 and not c['usage_complete'] for c in calls),
        classifications=dict(Counter(r['classification'] for r in rows)),independent_results_read=acceptance_completed,
        gate_accepted=sum(r['gate_accepted'] for r in rows),
        semantic_repair_qualified=sum(r['semantic_repair_qualified'] is True for r in rows),
        semantic_qualification_pending=sum(r['semantic_repair_qualified'] is None for r in rows),
        accepted_component_inactivity=sum(r['accepted_component_inactivity'] for r in rows),
        model_phase_native_compile_attempts=sum(r['native_compile_attempts'] for r in rows),
        model_phase_native_execution_attempts=sum(r['native_execution_attempts'] for r in rows),
        model_phase_native_seconds=sum(r['native_seconds'] for r in rows),
        model_phase_native_wall_seconds_excluding_lock_wait=sum(r['native_wall_seconds'] for r in rows),
        model_phase_shared_lock_wait_seconds=sum(r['shared_lock_wait_seconds'] for r in rows),
        independent_input_scope='Fresh generated inputs on development fault instances, not unseen-fault generalization.',
        protocol_sha256=seal['protocol_sha256'],new_model_calls_by_report=0,new_native_executions_by_report=0,
        accepted_legal_history=dict(rounds=len(history_audits),new_alarm_events=sum(len(r['new_legal_alarm_events_on_same_queries']) for r in history_audits),
            coarse_masked_events=sum(len(r['coarse_id_masked_new_legal_alarm_events']) for r in history_audits),
            unresolved_markers=sum(len(r['unresolved_native_marker_bindings']) for r in history_audits)))
    notes=['All registered arms, including blocked initial and generated failures, remain in the population.',
        'Targets/detected_ids/transaction_detected_ids are transaction-by-obligation target IDs. Timely and any-cycle target counts are not counts or rates of independently detected transactions. Unique transaction IDs and transactions with at least one detected obligation are reported separately.',
        'Budget truncation is a generation failure, not RTL infrastructure failure. Unknown native/reference outcomes are separate from known rejection.',
        'A rejected proposal may improve some metrics but has zero retained benefit; proposed gains and decisive history protection are recorded separately.',
        'Actual token costs come from physical result.json records, not declared budgets. Native shared-lock wait is separate from execution cost.',
        'Common known-token support does not equalize actual token spend; it retains pairs with completed independent evidence and measured usage in both arms.',
        'Pairs and seeds repeat the same parent design/fault; four fixture types are not four independent historical Bugs.',
        'An accepted aggregate FP improvement is not a successful local temporal repair if its edited component becomes finitely untriggered while another assertion preserves aggregate detection. Native per-component trigger markers and actual typed operators are reported separately.',
        'No isolated attribution from L-vs-F: P-vs-F separates localization hints and L-vs-P separates permission restrictions.',
        'UART archival replay causal eligibility is normalized in this report only; original artifacts are untouched.']
    conclusions=[
        '本轮没有证明局部编辑整体优于自由编辑：F/P/L 各 6 次真实调用，独立非空触发改善分别为 4/4/2；这是小样本、同故障新输入上的误报修复结果。',
        '窗口 F/P 修改响应的采样时序并减少合法误报；L 两次修改触发条件后，目标组件在开发和独立输入上均未触发。三组整体检出相同，不能用门控接受或整体检出掩盖组件失效。',
        '合法例外三组均减少误报且保留检出；事务匹配没有保留改善。L 两次错误收窄触发丢失历史目标，均由所有组共用的历史门拒绝。',
        '独立验收未发现新增目标检出：窗口和匹配各 14/16，例外 2/4，分母为事务×义务目标。延迟组初始未知，6 个身份未调用并保留初始，独立仍有未知，不计作通过。',
        '专用 set_delay/set_window/match_transaction/except_when 操作已做手写原生资格；本轮 L 实际模型提案使用 replace_field，不能把手写专用操作验证当成模型执行收益。',
        '独立 r01 因查询缺少 semantic_key 在 window q0 证据构造阶段失败；补元数据的 r02 保留全部原查询字段、种子和候选，16 次原生作业完成。r01 的 6 次作业成本单列保留。']
    cards=[]
    for row in rows:
        if row['fixture']!='window' or row['seed']!=19507 or row['arm'] not in ('F','L'):continue
        folder=Path(row['folder']);rd=folder/'round01'
        before=read(rd/'current_measurement.json',{});after=read(rd/'proposal_native/measurement.json',{})
        candidate=read(folder/'initial.json',[]);proposal=read(rd/'proposal.json',[])
        if not before or not proposal:continue
        def sva(assertions):
            return ['%s: assert property (@(posedge clk) disable iff(!rst_n) (%s) %s (%s));'%(a['label'],a['antecedent'],'|=>' if a['timing']=='next_sample' else '|->',a['consequent']) for a in assertions]
        before_events=[ev for ev in before.get('evidence',[]) if ev.get('variant')=='correct' and ev.get('status')=='confirmed'
            and ev.get('label')=='legal' and any(a.get('assertion')=='change_has_cause' and a.get('failure') for a in ev.get('assertions',[]))]
        cycles={ev['cycle'] for ev in before_events};wave=[]
        for job in before.get('executions',[]):
            if job.get('variant')!='correct':continue
            wave.extend(dict(query_id=job['query_id'],variant='correct',sample=sample)
                for sample in job['trace'] if any(abs(sample['cycle']-cycle)<=1 for cycle in cycles))
        cards.append(dict(id=row['id'],original_sva=sva(candidate),proposed_sva=sva(proposal),
            raw_model_edit=read(rd/'model_edit.json'),localization=read(rd/'localization.json',[]),
            key_waveform=wave,before_legal_alarm_evidence_ids=sorted({ev['id'] for ev in before_events}),
            development_component_activity=dict(before=row['before_component_activity'],after=row['after_component_activity']),
            gate=read(folder/'rounds.json',[{}])[-1].get('decision',{}),
            independent_component_activity=row.get('independent_component_activity'),
            independent_vs_initial=row.get('independent_vs_initial'),semantic_repair_qualified=row['semantic_repair_qualified'],
            semantic_qualification_reasons=row.get('semantic_qualification_reasons'),links=row['evidence_links'],
            interpretation='Actual model result. Gate acceptance and nonvacuous independent repair qualification are separate; finite inactivity is not a proof of logical vacuity.'))
    for name,data in [('summary.json',summary),('trajectories.json',rows),('calls.json',calls),('by_fixture_arm.json',aggregates),
        ('paired_results.json',pairs),('legal_history_audit.json',history_audits),('archival_provenance_normalization.json',normalization),('interpretation_notes.json',notes),
        ('phase_costs.json',phase_costs),('model_call_contract_audit.json',contract_audit),('conclusions.json',conclusions)]:dump(out/name,data)
    dump(out/'case_cards.json',cards)
    sections=token_sections(rows,grade_index) if acceptance_completed else dict(status='independent_pending')
    dump(out/'cost_sections.json',sections)
    report=dict(summary=summary,by_fixture_arm=aggregates,trajectories=rows,pairs=pairs,case_cards=cards,
        archival_provenance_normalization=normalization,phase_costs=phase_costs,model_call_contract_audit=contract_audit,notes=notes,
        conclusions=conclusions,cost_sections=sections,report_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    dump(out/'report.json',report)
    body=['<h1>REGuard research195 局部修改对照</h1><p>只读报告；归档重放不计作模型效果。未知与失败保留在完整总体。</p>',
        '<ul>'+''.join('<li>'+html.escape(item)+'</li>' for item in conclusions)+'</ul>',
        '<pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
        '<table><tr><th>类型</th><th>臂</th><th>调用</th><th>门接受</th><th>独立非空触发改善</th><th>Tokens</th><th>分类</th></tr>']
    for row in aggregates:body.append('<tr>'+''.join('<td>'+html.escape(str(row[k]))+'</td>' for k in ('fixture','arm','model_calls','accepted','semantic_repair_qualified','known_tokens','classifications'))+'</tr>')
    body+=['</table><h2>实际 token 完成前缀截面（事后只读）</h2><p>单次调用不可拆分；超预算截面保留初始。截断、拒绝、无变化的已完成调用仍全额计费。<a href="cost_sections.json">完整成本截面和共同支持明细</a>。</p>',
        '<table><tr><th>截面</th><th>臂</th><th>完成调用</th><th>前缀实际tokens</th><th>接受修改</th><th>非空触发改善</th></tr>']
    for section in sections.get('summary',[]):
        values=[section['token_cut'] if section['cut_kind']=='fixed' else '各配对最小实际tokens',section['arm'],section['completed_calls'],section['completed_prefix_tokens'],section['accepted_updates'],section['nonvacuous_improvements']]
        body.append('<tr>'+''.join('<td>'+html.escape(str(value))+'</td>' for value in values)+'</tr>')
    body+=['</table><h2>解释边界</h2><ul>']+['<li>'+html.escape(n)+'</li>' for n in notes]+['</ul>']
    body+=['<h2>窗口真实模型对照案例</h2>']
    for card in cards:body+=['<h3>'+html.escape(card['id'])+'</h3><pre>'+html.escape(json.dumps(card,ensure_ascii=False,indent=2))+'</pre>']
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:15px/1.5 system-ui;max-width:1200px;margin:32px auto}td,th{border:1px solid #ccd;padding:8px}table{border-collapse:collapse}pre{white-space:pre-wrap}</style>'+''.join(body),encoding='utf-8')
    print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','execution','independent','out','replay'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();analyze(args.prepared,args.execution,args.independent,args.out,args.replay)
