"""Record interrupted R3 native execution as unknown, dispatch only untouched arms.

No model or native retry. A filesystem exhaustion is not an algorithm regression.
The original fixed eight-call protocol and exact prepared requests stay intact.
"""
import argparse
import copy
import json
from pathlib import Path
import research192_temporal_refinement as r
import research192_refinement_run as sealed


def recover_incomplete(folder):
    if (folder/'result.json').exists():
        raise ValueError('already_terminal')
    model=r.s.read(folder/'model_call/result.json')
    initial=r.s.read(folder/'initial.json')
    proposal=r.s.read(folder/'model_call/candidate.json')
    baseline=r.s.read(folder/'baseline_measurement.json')
    protected=baseline['detected_ids']
    jobs=[]; missing=[]; compile_records=[]; execute_records=[]; attempted=[]
    for depth in r.p.q.DEPTHS:
        for policy in r.p.q.POLICIES:
            for revision in ('before','after'):
                path=folder/'native'/str(depth)/policy/revision
                result_path=path/'result.json'
                try:
                    result=r.s.read(result_path)
                    if 'compile_status' not in result or 'execution_status' not in result:raise ValueError('invalid_record')
                except (ValueError,OSError):
                    if result_path.exists():
                        raw=path/'result.interrupted.raw'
                        if raw.exists():raise ValueError('duplicate_recovery')
                        raw.write_bytes(result_path.read_bytes())
                    result=dict(compile_status='unknown',execution_status='not_completed',
                        failures=[],triggers=[],native_simulation_calls=None,
                        property_status='unknown',recovered_infrastructure_record=True,
                        error_type='ENOSPC',reason='Original process failed writing compile/result logs; no rerun or inferred semantic verdict.')
                    r.s.dump(result_path,result)
                    missing.append(r.s.rel(path))
                for name,bucket in [('compile.json',compile_records),('execute.json',execute_records)]:
                    try:bucket.append(r.s.read(path/name))
                    except (OSError,ValueError):pass
                if (path/'compile.json').exists() or (path/'compile.log').exists() or (path/'obj_dir').exists():
                    attempted.append(r.s.rel(path))
                jobs.append(dict(scene_id=f'{depth}/{policy}',depth=depth,policy=policy,
                    rows=r.p.q.rows(depth,policy),revision=revision,folder=str(path),result=result))
    if not missing:
        raise ValueError('expected_interrupted_R3_native_records_missing')
    measurement=r.binding.bound_measure(proposal,jobs,protected)
    if not measurement['critical_unknown']:raise ValueError('interruption_must_not_pass')
    r.s.dump(folder/'native/executions.json',jobs)
    r.s.dump(folder/'native/measurement.json',measurement)
    r.s.dump(folder/'measurement.json',measurement)
    decision=dict(accepted=False,regression=False,lost=[],new_false_positives=[],
        reason='infrastructure_unknown_retains_initial',
        unconfirmed_lost_due_to_incomplete_execution=measurement['lost'])
    r.s.dump(folder/'decision.json',decision)
    r.s.dump(folder/'terminal.json',initial)
    request=r.s.read(folder/'request.preview.json');seed=request['seed'];strategy=model['phase']
    r.s.dump(folder/'frozen.json',dict(candidate_sha256=r.p.digest(initial),seed=seed,strategy=strategy,
        freeze_before_independent=True,independent_results_not_used=True,
        reason='Initial retained because original proposal native suite was interrupted by disk exhaustion.'))
    result=dict(strategy=strategy,seed=seed,parent_bug='axis_fifo_oversize_atomic_drop',
        status=model['status'],candidate_generated=True,accepted=False,regression_proposals=0,
        accepted_regressions=0,final_detected=len(baseline['detected_ids']),
        final_targets=len(set(baseline['public_targets']+baseline['historical_targets'])),
        final_fp=len(baseline['false_positives']),
        final_fn=len(set(baseline['public_targets']+baseline['historical_targets'])-set(baseline['detected_ids'])),
        final_unknown=len(baseline['critical_unknown']),effective_rounds=0,model_calls=1,
        prompt_tokens=model['prompt_tokens'],completion_tokens=model['completion_tokens'],
        physical_native_compiles=len(attempted),logical_native_compiles=12,native_reuse_source=None,
        native_seconds=sum(v['wall_seconds'] for v in compile_records+execute_records),wall_seconds=None,
        incomplete_cost_records=True,native_compile_attempt_evidence=attempted,
        infrastructure_failure='disk_full',proposal_unknown=len(measurement['critical_unknown']),
        interrupted_native_jobs=missing,independent_acceptance='not_run_in_refinement_pilot',
        scope='One original FIFO parent; proposal semantics unknown for interrupted native cases, not an algorithm regression.')
    r.s.dump(folder/'result.json',result)
    r.s.dump(folder/'interruption_recovery.json',dict(model_retries=0,native_retries=0,
        known_failure='Observed original Python process OSError errno28 while writing compile.log and result.json.',
        incomplete_records=missing,final_candidate='unchanged initial',
        recovered_result_files='Only missing/unparseable native result files are replaced by explicit unknown markers; any original bytes remain in result.interrupted.raw.'))
    return result


def run(prepared,out):
    entries,initial,evidence,base=sealed.verify(prepared)
    already=list(out.glob('seed*/R*/model_call/attempt.json'))
    if len(already)!=4:raise ValueError('expected_exactly_four_previously_submitted_calls')
    if any((out/'seed19219'/strategy).exists() for strategy in r.STRATEGIES):
        raise ValueError('untouched_seed_only_no_retry')
    recovered=recover_incomplete(out/'seed19207/R3')
    rows=r.s.read(out/'results.json')
    if len(rows)!=3:raise ValueError('expected_three_completed_arm_records')
    rows.append(recovered);r.s.dump(out/'results.json',rows)
    protected=r.s.read(prepared/'baseline_measurement.json')['detected_ids']
    cache={}
    for row in rows:
        folder=out/f"seed{row['seed']}"/row['strategy']
        if row['candidate_generated'] and not row.get('infrastructure_failure'):
            candidate=r.s.read(folder/'model_call/candidate.json')
            cache[r.p.digest(dict(candidate=candidate,protected=sorted(protected)))]=dict(
                measurement=r.s.read(folder/'measurement.json'),source=r.s.rel(folder/'native'))
    r.s.dump(out/'continuation_protocol.json',dict(source_sha256=r.s.sha(Path(__file__)),
        scope='Only four as-yet-undispatched seed19219 arms; existing four model calls never repeated.',
        remaining_model_calls=4,total_model_call_cap=8,native_retries=0,model_retries=0,
        intervention='Remove reproducible current-batch compiler caches only after terminal jobs; preserve experiment inputs, executables, traces, logs, responses and outcomes.',
        infrastructure_failure_not_algorithm_regression=True))
    for item in [e for e in entries if e['seed']==19219]:
        sealed.verify(prepared)
        strategy=item['strategy'];folder=out/'seed19219'/strategy
        result=r.run_arm(folder,strategy,19219,evidence=evidence,initial=initial,
            protected=protected,base_request=base,native_cache=cache)
        if r.s.read(folder/'request.preview.json')!=r.s.read(r.ROOT/item['request']):
            raise ValueError('sealed_request_mismatch')
        rows.append(result);r.s.dump(out/'results.json',rows)
        print(json.dumps(result),flush=True)
    if len(list(out.glob('seed*/R*/model_call/attempt.json')))!=8:
        raise ValueError('physical_call_population')
    r.s.dump(out/'outcome.json',dict(status='completed_with_infrastructure_interruption',
        model_calls=8,all_requests_match_sealed=True,model_retries=0,native_retries=0,
        incomplete_native_arms=['seed19207/R3']))


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--prepared',required=True,type=Path)
    cli.add_argument('--out',required=True,type=Path)
    a=cli.parse_args();run(a.prepared.resolve(),a.out.resolve())
