"""Join real evidence, model edits and frozen acceptance without inventing wins."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import research194_report as report
import research194_cases as cases
from research194_metrics import temporal_detection
from research194_refinement_independent_pairs import fine_fp


def read(path,default=None):return report.read(Path(path),default)


def same_folder(a,b):return str(a).replace('\\','/').rstrip('/')==str(b).replace('\\','/').rstrip('/')


def round_termination(record):
    """Classify raw model outcomes before the runner's broad failure wrapper."""
    model=record.get('model',{});status=record.get('status');model_status=model.get('status')
    if model_status=='response_truncated' or model.get('done_reason')=='length':
        return 'budget_output_truncation'
    if status=='unknown_acquisition_or_history':return 'unknown_acquisition_or_history'
    if status=='infrastructure_interrupted':return 'infrastructure_interrupted'
    if status=='model_transport_or_decode_failure':
        if model_status in ('response_decode_failure','invalid_response','invalid_json'):return 'model_response_decode_failure'
        if model_status in ('transport_error','transport_failure','request_failed','timeout'):return 'model_transport_failure'
        return 'model_transport_or_decode_failure_unresolved'
    return 'completed_round_decision'


def trajectory_eligibility(row):
    """Comparable normal completion under the shared three-call ceiling."""
    folder=report.ROOT/row['folder'];rounds=read(folder/'rounds.json',[]);reasons=[]
    if row.get('status')!='frozen' or row.get('provenance')!='real_remote_model':reasons.append('not_real_model_frozen_trajectory')
    if row.get('causal_comparison_eligible') is not True:reasons.append('trajectory_marked_noncomparable')
    if row.get('termination_reason'):reasons.append(row['termination_reason'])
    classified=[dict(round=r.get('round'),outer_status=r.get('status'),classification=round_termination(r),
        model_status=r.get('model',{}).get('status'),done_reason=r.get('model',{}).get('done_reason'),
        completion_tokens=r.get('model',{}).get('completion_tokens')) for r in rounds]
    reasons.extend(sorted({r['classification'] for r in classified if r['classification']!='completed_round_decision'}))
    if not 0<=row.get('actual_model_calls',row.get('model_calls',0))<=3 or any(r.get('round',0)>3 for r in rounds):reasons.append('outside_shared_three_call_ceiling')
    configurations=[]
    for p in sorted(folder.glob('round*/request.preview.json')):
        req=read(p);index=int(p.parent.name[5:])-1
        config={k:req.get(k) for k in ('model','temperature','max_tokens')}
        config['base_seed']=req.get('seed',0)-index*1009
        if config['base_seed']!=row['seed']:reasons.append('paired_seed_schedule_mismatch')
        configurations.append(config)
    if len({json.dumps(c,sort_keys=True) for c in configurations})>1:reasons.append('within_trajectory_model_configuration_changed')
    return dict(eligible=not reasons,reasons=reasons,maximum_model_calls=3,actual_model_calls=row.get('actual_model_calls',row.get('model_calls',0)),
        itt_frozen_assignment_eligible=row.get('status')=='frozen' and row.get('provenance')=='real_remote_model',
        sealed_causal_comparison_eligible=row.get('causal_comparison_eligible'),raw_round_classifications=classified,
        full_three_round_decisions=len(rounds)==3 and all(r['classification']=='completed_round_decision' for r in classified),
        request_configuration=configurations[0] if configurations else None,
        stopping_rule='Three calls are a ceiling, not a claim that all trajectories completed three rounds. Budget output truncation retains its frozen version in intention-to-treat outcomes but cannot qualify as normal completed-round mechanism evidence. Raw classifications override a broad runner failure wrapper without editing sealed outcomes.')


def common_test_eligibility(current,comparison):
    left={r['fault']:r for r in current};right={r['fault']:r for r in comparison};reasons=[];unexposed=[]
    if not current or not comparison:reasons.append('missing_common_acceptance')
    if len(left)!=len(current) or len(right)!=len(comparison):reasons.append('duplicate_fault_grade')
    if set(left)!=set(right):reasons.append('different_fault_population')
    for fault in sorted(set(left)&set(right)):
        a,b=left[fault],right[fault]
        if set(a.get('target_ids',[]))!=set(b.get('target_ids',[])):reasons.append('different_target_population:'+fault)
        if bool(a.get('valid_reachable_fault'))!=bool(b.get('valid_reachable_fault')):reasons.append('different_fault_qualification:'+fault)
        if not a.get('native_complete') or not b.get('native_complete'):reasons.append('native_incomplete:'+fault)
        if a.get('unknown_records') or b.get('unknown_records') or not a.get('reference_complete') or not b.get('reference_complete'):reasons.append('unknown_acceptance:'+fault)
        if not a.get('valid_reachable_fault') or not a.get('target_ids'):unexposed.append(fault)
    return dict(eligible=not reasons,reasons=reasons,common_faults=sorted(set(left)&set(right)),
        excluded_unexposed_faults=unexposed,scope='Only common confirmed reachable targets support gains; unexposed faults are not passes or misses.')


def score(rows):
    good=[r for r in rows if r.get('valid_reachable_fault') and not r.get('unknown_records')]
    return dict(detected=set().union(*(set(r.get('transaction_detected_ids',[])) for r in good)),
        fp=sum(r.get('false_positive_records',0) for r in rows),unknown=sum(r.get('unknown_records',0) for r in rows))


def card(row,kind,mechanism,acceptance,comparison,reason):
    folder=report.ROOT/row['folder'];initial=read(folder/'initial.json',cases.get_case(row['case_id'])['initial'])
    acquired=read(folder/'acquisitions.json',[]);rounds=read(folder/'rounds.json',[])
    evidence=None;waveform=[];task=None
    bridge=None;terminal=read(folder/'terminal_measurement.json',{});frozen=read(folder/'frozen.json')
    terminal_bound=bool(terminal and frozen and terminal.get('candidate_sha256')==cases.digest(frozen)==row.get('frozen_sha256'))
    retained=set(temporal_detection(terminal)['transaction_detected_ids']) if terminal_bound else set()
    for record in rounds:
        if record.get('status')!='accepted':continue
        rd=folder/f'round{record["round"]:02}'
        before=read(rd/'current_measurement.json',{});after=read(rd/'proposal_native/measurement.json',{})
        if not before or not after:continue
        gained=set(temporal_detection(after)['transaction_detected_ids'])-set(temporal_detection(before)['transaction_detected_ids'])
        request=read(rd/'request.preview.json',{});messages=request.get('messages',[])
        context=json.loads(messages[-1]['content']) if messages else {}
        proposal=read(rd/'proposal.json')
        if before.get('candidate_sha256')!=cases.digest(context.get('current_assertions')) or not proposal or after.get('candidate_sha256')!=cases.digest(proposal):continue
        visible={e.get('id',e.get('evidence_id')) for e in context.get('development_observations',[]) if e.get('status')=='confirmed'}
        ids=gained & visible & retained
        if not ids:continue
        eid=sorted(ids)[0]
        event=next((e for e in before['evidence'] if e.get('evidence_id',e.get('id'))==eid and e.get('counted_target')),None)
        if event is None:continue
        evidence=event
        bridge=dict(round=record['round'],evidence_id=eid,actually_in_model_request=True,retained_by_final_frozen_candidate=True,
            final_candidate_bound=terminal_bound,final_measurement_path=str((folder/'terminal_measurement.json').relative_to(report.ROOT)),
            before_transaction_detected=False,after_transaction_detected=True,
            native_after_alarms=[e for e in after['evidence'] if e.get('evidence_id',e.get('id'))==eid and e.get('status')=='confirmed' and e.get('label')=='violation' and any(a.get('failure') for a in e.get('assertions',[]))],
            request_path=str((rd/'request.preview.json').relative_to(report.ROOT)),
            proposal_native_path=str((rd/'proposal_native/measurement.json').relative_to(report.ROOT)),
            candidate_before=context.get('current_assertions'),accepted_proposal=read(rd/'proposal.json'))
        job=next((j for j in before['executions'] if j['query_id']==event['query_id'] and j['variant']==event['variant']),None)
        if job:waveform=[x for x in job['trace'] if abs(x['cycle']-event['cycle'])<=4]
        task=next((a.get('task_id') for a in acquired if event['query_id'] in {q['id'] for q in a.get('queries',[])}),None)
        break
    for acq in acquired:
        if evidence is not None:break
        candidates=[e for e in acq.get('evidence',[]) if e.get('status')=='confirmed' and e.get('counted_target') and not any(a.get('failure') for a in e.get('assertions',[]))]
        if not candidates:continue
        evidence=candidates[0];task=acq.get('task_id',dict(query_id=evidence['query_id'],fault=acq.get('fault_id','primary')))
        job=next((j for j in acq['measurement'].get('executions',[]) if j['query_id']==evidence['query_id'] and j['variant']==evidence['variant']),None)
        if job:waveform=[x for x in job['trace'] if abs(x['cycle']-evidence['cycle'])<=4]
        break
    modifications=[]
    for path in sorted(folder.glob('round*/model_edit.json')):
        request=read(path.parent/'request.preview.json',{});messages=request.get('messages',[])
        context=json.loads(messages[-1]['content']) if messages else {}
        modifications.append(dict(round=path.parent.name,raw_model_edit=read(path),proposal=read(path.parent/'proposal.json'),
            localization=read(path.parent/'localization.json'),decision=next((r for r in rounds if r['round']==int(path.parent.name[5:])),None),
            localization_supplied_to_model='localization' in context,
            source=str(path.relative_to(report.ROOT))))
    return dict(kind=kind,mechanism=mechanism,selection_reason=reason,trajectory=row,
        evidence_to_edit_bridge=bridge,full_positive_chain=kind=='positive' and bridge is not None,
        original_sva=initial,modified_frozen_sva=read(folder/'frozen.json'),task_id=task,evidence=evidence,
        key_transaction_waveform=waveform,rounds=rounds,modifications=modifications,
        acceptance=acceptance,comparison_acceptance=comparison,
        attribution_limit='Paired observed outcome with exact evidence/edit links retained by the final candidate. A model may also use public RTL/specification; this is not proof that a single waveform alone caused its edit or a particular held-out gain.')


ITT_SELECTION_PROTOCOL=dict(version='r194_retained_version_appendix_v1',
    scope='Separate positive examples of interrupted retained versions; strict main cards are unchanged.',
    method_comparator={'active_search':['S3R1','S0R1'],'localized_refinement':['S0R3','S0R0']},
    candidate_interruptions=['budget_output_truncation','unhandled_interruption_retained_last_checkpoint'],
    requirements=['Same case, seed, nonempty initial hash, model configuration, parent and shared three-call ceiling.',
        'All planned fault grades exist for both versions, with equal confirmed target populations, native completion and no unknown.',
        'A real response_received accepted round improves a confirmed visible evidence ID, which remains detected by the final hash-bound candidate.',
        'Common independent transaction detection has a nonempty gain and no loss; confirmed legal alarm contexts (fault, query_id, variant, cycle, obligation) have no additions, ignoring assertion labels; coarse evidence IDs are provenance only.',
        'Only read independent grades, plans and projections after the completed marker.'],
    selection='At most one positive per mechanism: largest paired independent transaction gain; ties case_id then seed. A missing verified bridge produces no card, not a substituted example.',
    strict_metric_correction='Strict main-card selection and trajectory conditions remain unchanged. Its existing no-new-FP predicate is measured by legal alarm context set inclusion, not aggregate FP count.',
    interpretation='Observed retained-version outcome, not complete three-round execution, full-strategy acceptance, population superiority or single-waveform causal proof.')


def register_itt(out):
    out=Path(out);path=out/'itt_selection_protocol.json'
    if path.exists() and read(path)!=ITT_SELECTION_PROTOCOL:raise ValueError('itt_selection_rule_changed')
    if not path.exists():report.dump(path,ITT_SELECTION_PROTOCOL)
    return path


def independent_fp_binding(independent,row,grades):
    """Candidate-bound actual FP identities, not just a possibly equal count."""
    mapping_path=independent/row['case_id']/'version_mapping.json';mapping=read(mapping_path,{})
    expected=row.get('frozen_sha256');keys=mapping.get('keys',[]);reasons=[];ids=set();units=set();paths=[]
    if not expected or keys.count(expected)!=1:return dict(eligible=False,reasons=['missing_unique_frozen_version_mapping'],fp_ids=[],fp_units=[])
    index=keys.index(expected)
    for grade in grades:
        path=independent/row['case_id']/grade['fault']/f'projection{index}.json';measurement=read(path,{})
        if measurement.get('candidate_sha256')!=expected:
            reasons.append('projection_candidate_mismatch:'+grade['fault']);continue
        if set(measurement.get('targets',[]))!=set(grade.get('target_ids',[])):
            reasons.append('projection_grade_target_mismatch:'+grade['fault'])
        fps=measurement.get('false_positives',[])
        if len(fps)!=grade.get('false_positive_records'):reasons.append('projection_grade_fp_count_mismatch:'+grade['fault'])
        for event in fps:
            eid=event.get('evidence_id',event.get('id'))
            if not eid or event.get('status')!='confirmed' or event.get('label')!='legal':
                reasons.append('unconfirmed_fp_identity:'+grade['fault']);continue
            ids.add((grade['fault'],eid))
        units.update((grade['fault'],*unit) for unit in fine_fp(measurement))
        paths.append(path)
    return dict(eligible=not reasons,reasons=sorted(set(reasons)),fp_ids=[list(x) for x in sorted(ids)],fp_units=[list(x) for x in sorted(units,key=str)],
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [mapping_path,*paths]})


def fp_context_comparison(current,comparison):
    added=set(map(tuple,current.get('fp_units',[])))-set(map(tuple,comparison.get('fp_units',[])))
    bound=bool(current.get('eligible') and comparison.get('eligible'))
    return dict(bindings_complete=bound,added_units=[list(x) for x in sorted(added,key=str)],no_new_fp=bound and not added)


def build_itt(main,independent,out):
    """An explicitly separate appendix; never relax strict primary cards."""
    main,independent,out=Path(main),Path(independent),Path(out);protocol_path=register_itt(out)
    if read(independent/'outcome.json',{}).get('status')!='completed':
        result=dict(status='awaiting_completed_independent_acceptance',independent_grades_read=False,cards=[],model_calls=0,native_executions=0)
        report.dump(out/'itt_status.json',result);return result
    grades=read(independent/'results.json',[]);plan=read(independent/'plan.json',{});rows=report.trajectories(main)
    selected=[];eligibility=[]
    for mechanism,search,strategy,baseline in [('active_search','S3','R1','R1'),('localized_refinement','S0','R3','R0')]:
        possible=[]
        for row in rows:
            if (row.get('search_strategy'),row['strategy'])!=(search,strategy):continue
            pair=next((p for p in rows if (p['case_id'],p['seed'],p.get('search_strategy'),p['strategy'])==(row['case_id'],row['seed'],'S0',baseline)),None)
            current=[g for g in grades if same_folder(g.get('folder'),row['folder'])]
            comparison=[g for g in grades if pair and same_folder(g.get('folder'),pair['folder'])]
            q=trajectory_eligibility(row);pq=trajectory_eligibility(pair) if pair else dict(eligible=False,reasons=['missing_pair'])
            interruption=[c['classification'] for c in q.get('raw_round_classifications',[]) if c['classification']=='budget_output_truncation']
            if row.get('termination_reason')=='unhandled_interruption_retained_last_checkpoint':interruption.append(row['termination_reason'])
            expected=set(plan.get(row['case_id'],{}).get('faults',[]))
            common=common_test_eligibility(current,comparison)
            checks=dict(known_interrupted_retained_version=bool(interruption),
                real_model_frozen_pair=bool(q.get('itt_frozen_assignment_eligible') and pq.get('itt_frozen_assignment_eligible')),
                same_initial=bool(pair and row.get('initial_sha256') and row['initial_sha256']==pair.get('initial_sha256')),
                same_model=bool(q.get('request_configuration') and q.get('request_configuration')==pq.get('request_configuration')),
                same_parent=bool(pair and row.get('parent_bug') and row['parent_bug']==pair.get('parent_bug')),
                within_shared_budget=all(0<=v.get('actual_model_calls',0)<=3 and 'outside_shared_three_call_ceiling' not in v.get('reasons',[]) for v in (q,pq)),
                complete_planned_fault_population=bool(expected) and set(g['fault'] for g in current)==set(g['fault'] for g in comparison)==expected,
                common_test=common['eligible'],
                frozen_candidate_grade_binding=bool(current and comparison and all(g.get('candidate_sha256')==row.get('frozen_sha256') for g in current) and all(g.get('candidate_sha256')==pair.get('frozen_sha256') for g in comparison)))
            a,b=score(current),score(comparison);gains=a['detected']-b['detected'];losses=b['detected']-a['detected']
            fp_a=independent_fp_binding(independent,row,current) if all(checks.values()) else dict(eligible=False,reasons=['preceding_qualification_failed'],fp_ids=[],fp_units=[])
            fp_b=independent_fp_binding(independent,pair,comparison) if all(checks.values()) else dict(eligible=False,reasons=['preceding_qualification_failed'],fp_ids=[],fp_units=[])
            fp_change=fp_context_comparison(fp_a,fp_b)
            positive=all(checks.values()) and bool(gains) and not losses and fp_change['no_new_fp']
            qualification=dict(current=q,comparison=pq,common_test=common,checks=checks,interruption_reasons=sorted(set(interruption)),
                current_fp_binding=fp_a,comparison_fp_binding=fp_b,current_error={k:row.get(k) for k in ('termination_reason','error_type','error')},
                strict_primary_eligible=q['eligible'] and pq.get('eligible',False))
            record=dict(mechanism=mechanism,case_id=row['case_id'],seed=row['seed'],folder=row['folder'],
                positive_outcome_before_bridge_check=bool(positive),gained_ids=sorted(gains),lost_ids=sorted(losses),
                new_fp_units=fp_change['added_units'],qualification=qualification)
            eligibility.append(record)
            if positive:possible.append((row,current,comparison,record))
        chosen=None
        for row,current,comparison,record in sorted(possible,key=lambda x:(-len(x[3]['gained_ids']),x[0]['case_id'],x[0]['seed'])):
            item=card(row,'positive',mechanism,current,comparison,dict(rule=ITT_SELECTION_PROTOCOL['selection'],
                comparator='S0'+baseline+' same case/seed',gained_ids=record['gained_ids'],lost_ids=record['lost_ids'],
                new_fp_units=record['new_fp_units'],qualification=record['qualification'],posthoc_example_selection=True,not_a_population_advantage_claim=True))
            bridge=item.get('evidence_to_edit_bridge');accepted=next((r for r in item['rounds'] if bridge and r['round']==bridge['round']),{})
            if not item.get('full_positive_chain') or accepted.get('model',{}).get('status')!='response_received':
                record['bridge_rejection']='no_retained_evidence_bridge_from_real_received_accepted_response';continue
            item.update(analysis_view='ITT_retained_version_appendix',not_complete_three_round_execution=True,
                whole_strategy_pass_claim=False,trajectory_qualification=record['qualification'],
                interpretation=ITT_SELECTION_PROTOCOL['interpretation'])
            chosen=item;break
        selected.append(chosen or dict(mechanism=mechanism,kind='positive',analysis_view='ITT_retained_version_appendix',
            status='no_qualifying_observed_retained_version_chain',reason='No interrupted frozen version met every fixed common-test, real-model, retained-evidence and no-new-FP requirement.'))
    source_paths=[Path(__file__),Path(report.__file__),Path(__file__).with_name('research194_refinement_independent_pairs.py'),protocol_path,independent/'outcome.json',independent/'results.json',independent/'plan.json']
    result=dict(status='completed',independent_grades_read=True,cards=selected,model_calls=0,native_executions=0,
        positive_cards=sum(bool(c.get('full_positive_chain')) for c in selected),
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths})
    report.dump(out/'itt_case_cards.json',selected);report.dump(out/'itt_eligibility.json',eligibility);report.dump(out/'itt_status.json',{k:v for k,v in result.items() if k!='cards'})
    body=['<h1>ITT 附录：中断后保留版本的正面证据链</h1><p>本附录独立于严格主卡。截断或外层异常不会消除已确认的保留版本收益，也不代表完成三轮、整条策略通过或总体优势。</p>']
    for item in selected:body.append('<h2>'+html.escape(item['mechanism'])+'</h2><pre>'+html.escape(json.dumps(item,ensure_ascii=False,indent=2))+'</pre>')
    (out/'itt_case_cards.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>REGuard ITT 保留版本附录</title><style>body{font:15px/1.5 system-ui;max-width:1200px;margin:32px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f8;padding:16px}</style><body>'+''.join(body)+'</body></html>',encoding='utf-8')
    return result


def build(main,independent,out):
    rows=report.trajectories(main);acceptance_completed=read(independent/'outcome.json',{}).get('status')=='completed'
    grades=read(independent/'results.json',[]) if acceptance_completed else [];cards=[];eligibility=[]
    for mechanism in ('active_search','localized_refinement'):
        candidates=[r for r in rows if (r.get('search_strategy')=='S3' and r['strategy']=='R1' if mechanism=='active_search' else r.get('search_strategy')=='S0' and r['strategy']=='R3')]
        scored=[]
        for row in candidates:
            current=[g for g in grades if same_folder(g.get('folder'),row['folder'])]
            if mechanism=='active_search':
                pair=next((r for r in rows if r['case_id']==row['case_id'] and r['seed']==row['seed'] and r.get('search_strategy')=='S0' and r['strategy']=='R1'),None)
                comparison=[g for g in grades if pair and same_folder(g.get('folder'),pair['folder'])]
            else:
                pair=next((r for r in rows if r['case_id']==row['case_id'] and r['seed']==row['seed'] and r.get('search_strategy')=='S0' and r['strategy']=='R0'),None)
                comparison=[g for g in grades if pair and same_folder(g.get('folder'),pair['folder'])]
            initial_control=[g for g in grades if g.get('role')=='initial_control' and g['case_id']==row['case_id']]
            a,b=score(current),score(comparison)
            gains=a['detected']-b['detected'];losses=b['detected']-a['detected']
            qualification=dict(current=trajectory_eligibility(row),comparison=trajectory_eligibility(pair) if pair else dict(eligible=False,reasons=['missing_paired_trajectory']),
                common_test=common_test_eligibility(current,comparison))
            same_initial=bool(pair) and row.get('initial_sha256')==pair.get('initial_sha256')
            same_model=qualification['current'].get('request_configuration')==qualification['comparison'].get('request_configuration')
            qualification.update(same_initial=same_initial,same_model_configuration=same_model,acceptance_completed=acceptance_completed)
            eligible=acceptance_completed and same_initial and same_model and all(qualification[k]['eligible'] for k in ('current','comparison','common_test'))
            fp_a=independent_fp_binding(independent,row,current) if eligible else dict(eligible=False,fp_units=[],reasons=['preceding_qualification_failed'])
            fp_b=independent_fp_binding(independent,pair,comparison) if eligible else dict(eligible=False,fp_units=[],reasons=['preceding_qualification_failed'])
            fp_change=fp_context_comparison(fp_a,fp_b)
            qualification.update(current_fp_binding=fp_a,comparison_fp_binding=fp_b,new_fp_units=fp_change['added_units'])
            eligible=eligible and fp_a['eligible'] and fp_b['eligible']
            positive=eligible and bool(gains) and not losses and fp_change['no_new_fp'] and row.get('accepted_rounds',0)>0
            eligibility.append(dict(mechanism=mechanism,case_id=row['case_id'],seed=row['seed'],folder=row['folder'],eligible=eligible,
                positive_outcome_before_bridge_check=positive,gained_ids=sorted(gains),lost_ids=sorted(losses),qualification=qualification))
            scored.append(dict(row=row,current=current,comparison=comparison,gains=gains,losses=losses,positive=positive,eligible=eligible,qualification=qualification,initial_control=initial_control))
        for kind in ('positive','failure'):
            pool=[x for x in scored if x['positive']] if kind=='positive' else [x for x in scored if x['eligible'] and not x['positive']]
            if not pool:
                cards.append(dict(mechanism=mechanism,kind=kind,status='no_qualifying_observed_chain',
                    reason='Requires completed real model trajectory and common frozen acceptance; no handwritten or incomplete run substituted.'));continue
            selected=None
            for chosen in sorted(pool,key=lambda x:(-len(x['gains']) if kind=='positive' else -len(x['losses']),x['row']['case_id'],x['row']['seed'])):
                reason=dict(rule='largest paired common-test transaction detection gain with a confirmed evidence/edit bridge and no lost detection/new FP; failure maximizes lost detection; ties case/seed',
                    comparator='S0R1 same case/seed' if mechanism=='active_search' else 'S0R0 same case/seed',
                    gained_ids=sorted(chosen['gains']),lost_ids=sorted(chosen['losses']),posthoc_example_selection=True,
                    not_a_population_advantage_claim=True,qualification=chosen['qualification'])
                candidate=card(chosen['row'],kind,mechanism,chosen['current'],chosen['comparison'],reason)
                candidate['initial_control_acceptance']=chosen['initial_control']
                candidate['initial_control_attribution']='Context only; improvement over an initial candidate cannot identify the localized-refinement mechanism.'
                if kind=='failure' or candidate['full_positive_chain']:
                    selected=candidate;break
            cards.append(selected or dict(mechanism=mechanism,kind=kind,status='no_qualifying_observed_chain',reason='Observed final gain lacks a verified same-evidence native before/after improvement in a real model round.'))
    out.mkdir(parents=True,exist_ok=True);report.dump(out/'case_cards.json',cards);report.dump(out/'eligibility.json',eligibility)
    body=['<h1>机制正反案例：证据到冻结验收</h1><p>选择规则公开；不存在符合条件的完整链时保留缺失，不拼接或用手写断言代替模型结果。</p>']
    for item in cards:
        body.append('<h2>'+html.escape(item['mechanism']+' / '+item['kind'])+'</h2>')
        body.append('<pre>'+html.escape(json.dumps(item,ensure_ascii=False,indent=2))+'</pre>')
    (out/'case_cards.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>REGuard 机制证据链</title><style>body{font:15px/1.5 system-ui;max-width:1200px;margin:32px auto;padding:20px;color:#203040}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f8;padding:16px}</style><body>'+''.join(body)+'</body></html>',encoding='utf-8')
    build_itt(main,independent,out)
    return cards


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--main',type=Path,required=True);p.add_argument('--independent',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--itt-only',action='store_true');p.add_argument('--register-itt',action='store_true')
    args=p.parse_args()
    if args.register_itt:register_itt(args.out)
    elif args.itt_only:build_itt(args.main,args.independent,args.out)
    else:build(args.main,args.independent,args.out)
