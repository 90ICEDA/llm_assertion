"""Read-only analysis of sealed R194 execution; never imports its runtime.

Incomplete files are reported as pending. This module cannot dispatch a model,
modify a candidate, change an execution verdict, or access independent inputs.
"""
import argparse
from collections import defaultdict
import hashlib
import html
import json
from pathlib import Path
import time


def read(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError,PermissionError):return default
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def identity(folder,root):
    bundle,case,seed,arm,*_=folder.relative_to(root).parts
    if bundle=='base':search,strategy=arm.split('_');condition=None
    else:search='augmentation_'+arm;strategy='R3';condition=arm
    return dict(bundle=bundle,case_id=case,seed=int(seed),arm=arm,search=search,strategy=strategy,condition=condition)


def request_context(folder):
    request=read(folder/'request.json') or read(folder.parent/'request.preview.json')
    if not request:return {},{}
    for msg in request.get('messages',[]):
        if msg.get('role')=='user':
            try:return request,json.loads(msg['content'])
            except (KeyError,json.JSONDecodeError):pass
    return request,{}


def model_stage(context):
    schema=context.get('output_contract',{}).get('schema',{})
    receipt=context.get('fallback_receipt') or {}
    if 'assertions' in schema:return 'regenerate' if receipt.get('stage')=='compose' else 'free'
    edits=schema.get('edits',[])
    if edits and edits[0].get('op')=='add_assertion':return 'compose'
    if 'edits' in schema:return 'local'
    return 'unknown'


def oracle_view(records):
    """Exclude candidate predictions and file paths, preserve oracle visibility."""
    rows=[]
    for ev in records:
        rows.append({key:ev.get(key) for key in ('id','status','label','obligation','query_id','transaction_id','cycle','variant','counted_target','observations','previous_observations')})
    return sorted(rows,key=lambda x:(str(x['id']),str(x['cycle']),str(x['variant'])))


def analyze(root,out):
    root=Path(root).resolve();out=Path(out).resolve();calls=[];trajectories=[];pending=[];ledger=[]
    for bundle in ('base','augmentation'):
        for row in read(root/bundle/'global_model_ledger.json',[]) or []:ledger.append(dict(row,bundle=bundle))
        for folder in sorted((root/bundle).glob('*/*/*/refinement')):
            ident=identity(folder,root);rounds={x['round']:x for x in read(folder/'rounds.json',[]) or []}
            terminal=read(folder/'outcome.json');history=read(folder/'controller_history.json',[]) or []
            last_round=rounds[max(rounds)] if rounds else {}
            native=read(folder/'terminal_measurement.json',{}) or {}
            trajectories.append(dict(ident,terminal=terminal is not None,status=terminal.get('status') if terminal else 'running',
                termination_reason=terminal.get('termination_reason') if terminal else None,
                last_recorded_round_status=last_round.get('status'),
                posthoc_terminal_cause=('bounded_response_truncation' if last_round.get('model',{}).get('status')=='response_truncated' else last_round.get('status')) if terminal else None,
                causal_comparison_eligible=terminal.get('causal_comparison_eligible') if terminal else None,
                initial_sha256=(terminal or {}).get('initial_sha256'),frozen_sha256=(terminal or {}).get('frozen_sha256'),
                model_calls=(terminal or {}).get('model_calls'),native_compile_attempts=(terminal or {}).get('native_compile_attempts'),
                final_timely_detected=len(native.get('detected_ids',[])),final_transaction_detected=len(native.get('transaction_detected_ids',[])),
                final_targets=len(native.get('targets',[])),final_false_positives=len(native.get('false_positives',[])),
                final_unknown=len(native.get('critical_unknown',[])),
                structural_empty_domain_certificates=sum(h.get('event')=='structural_local_domain_empty' for h in history),
                natively_measured_local_failures=sum(h.get('event')=='native_measured' and h.get('stage')=='local' and not h['decision']['accepted'] and h['decision']['semantic_failure'] for h in history),
                natively_measured_composition_failures=sum(h.get('event')=='native_measured' and h.get('stage')=='compose' and not h['decision']['accepted'] and h['decision']['semantic_failure'] for h in history),
                path=str(folder)))
            for model_folder in sorted(folder.glob('round*/model_call')):
                round_index=int(model_folder.parent.name.replace('round',''));result=read(model_folder/'result.json')
                request,context=request_context(model_folder)
                if result is None:
                    pending.append(dict(ident,round=round_index,attempt=read(model_folder/'attempt.json'),path=str(model_folder)));continue
                recorded=rounds.get(round_index,{})
                attempt=read(model_folder/'attempt.json',{}) or {}
                decision=recorded.get('decision',{})
                history_row=next((h for h in history if h.get('round')==round_index and h.get('event')!='structural_local_domain_empty'),{})
                if not decision:decision=history_row.get('decision',{})
                receipt=context.get('fallback_receipt') or {}
                classification=('structural_empty_domain' if receipt.get('kind')=='local_domain_empty' else 'measured_failed_proposal' if receipt.get('failed') else 'none')
                prompt=result.get('prompt_tokens');completion=result.get('completion_tokens')
                calls.append(dict(ident,round=round_index,stage=model_stage(context),fallback_authorization=classification,
                    fallback_source_stage=receipt.get('stage'),
                    result_status=result.get('status'),candidate_status=result.get('candidate_status'),
                    runner_status=recorded.get('status','pending_native_or_controller'),
                    frontend_error=recorded.get('error') or result.get('candidate_error'),
                    accepted=recorded.get('status')=='accepted',
                    proposed_gate_regression=bool(decision.get('regression')),
                    proposed_history_regression=bool(decision.get('lost_ids') or decision.get('historical_any_cycle_lost_ids')),
                    accepted_history_regression=recorded.get('status')=='accepted' and bool(decision.get('lost_ids') or decision.get('historical_any_cycle_lost_ids')),
                    new_false_positive_ids=decision.get('new_false_positive_ids',[]),
                    fixed_false_positive_ids=decision.get('fixed_false_positive_ids',[]),
                    history_guard_changes_acceptance=(recorded.get('status')=='rejected'
                        and ident['strategy'] in ('R2','R3')
                        and bool(decision.get('lost_ids') or decision.get('historical_any_cycle_lost_ids'))
                        and bool(decision.get('timely_gained_ids') or decision.get('transaction_gained_ids') or decision.get('fixed_false_positive_ids'))
                        and not decision.get('critical_unknown') and not decision.get('new_false_positive_ids')),
                    timely_gained_ids=decision.get('timely_gained_ids',[]),transaction_gained_ids=decision.get('transaction_gained_ids',[]),
                    timely_lost_ids=decision.get('lost_ids',[]),any_cycle_history_lost_ids=decision.get('historical_any_cycle_lost_ids',[]),
                    critical_unknown=decision.get('critical_unknown',[]),
                    model_calls=result.get('model_calls',1),prompt_tokens=prompt,completion_tokens=completion,
                    tokens_known=(prompt+completion if isinstance(prompt,int) and isinstance(completion,int) else None),
                    provider_response_id=result.get('response_id'),provider_model=result.get('actual_server_model'),
                    requested_seed=request.get('seed'),requested_model=request.get('model'),
                    requested_max_output=request.get('max_tokens'),model_wall_seconds=result.get('wall_seconds'),
                    recorded_endpoint=result.get('endpoint'),recorded_retries=result.get('retries'),
                    recorded_timeout_seconds=attempt.get('timeout_seconds'),
                    fixed_transport_contract_matches=(request.get('model')=='deepseek/deepseek-v3-0324'
                        and request.get('max_tokens')==2048 and result.get('endpoint')=='https://api.highwayapi.ai/openai/chat/completions'
                        and result.get('retries')==0 and attempt.get('timeout_seconds')==300),
                    request_sha256=digest(request),first_visible_oracle_sha256=digest(oracle_view(context.get('development_observations',[]))) if round_index==1 else None,
                    record_path=str(model_folder/'result.json')))
    groups=defaultdict(list)
    for trajectory in trajectories:
        records=[c for c in calls if all(c[k]==trajectory[k] for k in ('bundle','case_id','seed','arm'))]
        trajectory['observed_actual_model_calls']=sum(c['model_calls'] for c in records)
        trajectory['observed_known_tokens']=sum(c['tokens_known'] or 0 for c in records)
        trajectory['observed_unknown_usage_calls']=sum(c['tokens_known'] is None for c in records)
        trajectory['observed_accepted_rounds']=sum(c['accepted'] for c in records)
        trajectory['model_cost_basis']='actual persisted round/model_call/result.json, including outer-wrapper interruptions; original outcome unchanged'
    for call in calls:groups[(call['bundle'],call['search'],call['strategy'],call['stage'])].append(call)
    summaries=[]
    for key,rows in sorted(groups.items()):
        bundles,search,strategy,stage=key
        summaries.append(dict(bundle=bundles,search=search,strategy=strategy,stage=stage,
            completed_model_calls=sum(x['model_calls'] for x in rows),accepted_rounds=sum(x['accepted'] for x in rows),
            interface_rejected=sum(x['runner_status']=='interface_rejected' for x in rows),
            bounded_response_truncation=sum(x['result_status']=='response_truncated' for x in rows),
            model_transport_or_decode_failure=sum(x['runner_status']=='model_transport_or_decode_failure' for x in rows),
            valid_byte_identical_noop_rounds=sum(x['runner_status']=='no_change' for x in rows),
            valid_native_proposals=sum(x['runner_status'] in ('accepted','rejected') for x in rows),
            native_rejected_without_known_gain=sum(x['runner_status']=='rejected' and not x['critical_unknown'] and not x['timely_gained_ids'] and not x['transaction_gained_ids'] for x in rows),
            pending_native_or_controller=sum(x['runner_status']=='pending_native_or_controller' for x in rows),
            unknown_proposals=sum(bool(x['critical_unknown']) for x in rows),
            proposed_history_regression_rounds=sum(x['proposed_history_regression'] for x in rows),
            proposed_gate_regression_rounds=sum(x['proposed_gate_regression'] for x in rows),
            proposed_new_legal_alarm_rounds=sum(bool(x['new_false_positive_ids']) for x in rows),
            history_guard_changes_acceptance_rounds=sum(x['history_guard_changes_acceptance'] for x in rows),
            accepted_history_regression_rounds=sum(x['accepted_history_regression'] for x in rows),
            unique_any_cycle_history_losses=len({i for x in rows for i in x['any_cycle_history_lost_ids']}),
            known_tokens=sum(x['tokens_known'] or 0 for x in rows),unknown_token_calls=sum(x['tokens_known'] is None for x in rows),
            structural_certificate_calls=sum(x['fallback_authorization']=='structural_empty_domain' for x in rows),
            measured_failure_authorized_calls=sum(x['fallback_authorization']=='measured_failed_proposal' for x in rows)))
        summaries[-1]['actual_local_failure_to_composition_calls']=sum(x['stage']=='compose' and x['fallback_authorization']=='measured_failed_proposal' and x['fallback_source_stage']=='local' for x in rows)
        summaries[-1]['actual_composition_failure_to_regeneration_calls']=sum(x['stage']=='regenerate' and x['fallback_authorization']=='measured_failed_proposal' and x['fallback_source_stage']=='compose' for x in rows)
    paired=[]
    for case in ('arbiter','counter','uart','ibex_flush'):
        for seed in (19407,19419):
            arm_calls={x['strategy']:x for x in calls if x['bundle']=='base' and x['case_id']==case and x['seed']==seed and x['search']=='S0' and x['round']==1}
            arm_folders={x['strategy']:Path(x['path']) for x in trajectories if x['bundle']=='base' and x['case_id']==case and x['seed']==seed and x['search']=='S0'}
            stimuli={}
            for strategy,folder in arm_folders.items():
                rows=read(folder/'acquisitions.json')
                if rows is not None:stimuli[strategy]=[digest(q['rows']) for acq in rows for q in acq.get('queries',[])]
            rounds_equal=[]
            for i in range(3):
                present={k:v[i] for k,v in stimuli.items() if len(v)>i}
                rounds_equal.append(dict(round=i+1,available_arms=sorted(present),same_submitted_input_when_present=len(set(present.values()))<=1,
                    complete_four_arm_comparison=len(present)==4))
            paired.append(dict(case_id=case,seed=seed,first_model_calls_present=sorted(arm_calls),
                first_same_visible_oracle_evidence=(len({x['first_visible_oracle_sha256'] for x in arm_calls.values()})==1 if arm_calls else None),
                first_comparison_complete=len(arm_calls)==4,input_schedule_checks=rounds_equal,
                qualification='Only complete four-arm paired comparisons support same-evidence conclusions; candidate predictions necessarily change after edits.'))
    model_phase_complete=sum(t['terminal'] for t in trajectories)==80 and not pending
    report=dict(status='model_phase_complete_read_only' if model_phase_complete else 'incremental_read_only',
        model_phase_complete=model_phase_complete,snapshot_unix=time.time(),root=str(root),sealed_files_modified=False,
        model_requests_submitted_by_this_analysis=0,ledger_reserved_slots=len(ledger),completed_model_result_records=len(calls),
        completed_actual_model_calls=sum(c['model_calls'] for c in calls),pending_model_call_folders=len(pending),
        terminal_trajectories=sum(t['terminal'] for t in trajectories),visible_trajectories=len(trajectories),
        provider_response_ids_unique=len({c['provider_response_id'] for c in calls if c['provider_response_id']}),
        known_tokens=sum(c['tokens_known'] or 0 for c in calls),unknown_token_calls=sum(c['tokens_known'] is None for c in calls),
        bounded_response_truncation=sum(c['result_status']=='response_truncated' for c in calls),
        fixed_transport_contract_mismatches=sum(not c['fixed_transport_contract_matches'] for c in calls),
        notes=['First R3 composition may be authorized by structural local_domain_empty; do not relabel it as a measured failed local edit.',
               'Protected-history regression rounds can repeat the same historical loss; unique loss IDs are reported separately.',
               'Gate regression includes new false alarms; historical detection loss and novel legal alarms are split to avoid attributing FP rejection to historical protection.',
               'Requested provider seed does not establish deterministic sampling.',
               'No independent acceptance inputs or outcomes are read.'])
    refinement_table=[]
    for strategy in ('R0','R1','R2','R3'):
        arm=[c for c in calls if c['bundle']=='base' and c['search']=='S0' and c['strategy']==strategy]
        population=[t for t in trajectories if t['bundle']=='base' and t['search']=='S0' and t['strategy']==strategy]
        accepted=sum(c['accepted'] for c in arm)
        natives=sum(c['runner_status'] in ('accepted','rejected') for c in arm)
        refinement_table.append(dict(strategy=strategy,search='S0',registered_population=8,
            terminal_population=sum(t['terminal'] for t in population),actual_model_calls=sum(c['model_calls'] for c in arm),
            accepted_rounds=accepted,accepted_real_local_rounds=sum(c['accepted'] and c['stage']=='local' for c in arm),
            accepted_composition_rounds=sum(c['accepted'] and c['stage']=='compose' for c in arm),
            accepted_regeneration_rounds=sum(c['accepted'] and c['stage']=='regenerate' for c in arm),
            native_proposals=natives,acceptance_per_model_call=accepted/len(arm) if arm else None,
            acceptance_per_native_proposal=accepted/natives if natives else None,
            interface_rejections=sum(c['runner_status']=='interface_rejected' for c in arm),
            byte_identical_noops=sum(c['runner_status']=='no_change' for c in arm),
            output_budget_truncations=sum(c['result_status']=='response_truncated' for c in arm),
            unknown_native_proposals=sum(bool(c['critical_unknown']) for c in arm),
            proposed_new_legal_alarm_rounds=sum(bool(c['new_false_positive_ids']) for c in arm),
            proposed_history_loss_rounds=sum(c['proposed_history_regression'] for c in arm),
            accepted_history_loss_rounds=sum(c['accepted_history_regression'] for c in arm),
            history_guard_decisive_rejections=sum(c['history_guard_changes_acceptance'] for c in arm),
            known_tokens=sum(c['tokens_known'] or 0 for c in arm),unknown_usage_calls=sum(c['tokens_known'] is None for c in arm)))
    dump(out/'refinement_strategy_development_table.json',dict(rows=refinement_table,
        qualification='Observed S0 development execution/cost only. Initial, seeds and stimuli are paired; unknown/early stop can change exposure. Final quality requires shared independent fault-target pairing.'))
    for name,value in [('summary',report),('calls',calls),('trajectories',trajectories),('by_strategy_and_stage',summaries),('paired_same_evidence',paired),('pending',pending)]:dump(out/(name+'.json'),value)
    columns=('bundle','search','strategy','stage','completed_model_calls','accepted_rounds','interface_rejected','valid_byte_identical_noop_rounds','unknown_proposals','proposed_history_regression_rounds','accepted_history_regression_rounds','known_tokens','unknown_token_calls')
    table='<tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in columns)+'</tr>'
    for row in summaries:table+='<tr>'+''.join('<td>'+html.escape(str(row[c]))+'</td>' for c in columns)+'</tr>'
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>R194 refinement posthoc</title><style>body{font:15px system-ui;margin:35px}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #aaa}</style><h1>Read-only refinement snapshot</h1><p>'+html.escape(json.dumps(report,ensure_ascii=False))+'</p><table>'+table+'</table><p>Counts are provisional while calls/native gates are pending. No new execution, request, or verdict is introduced.</p>',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--campaign',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();analyze(a.campaign,a.out)
