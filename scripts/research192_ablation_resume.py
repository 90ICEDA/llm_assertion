"""Record the disk-full interrupted arm without retry, then dispatch only unsent arms.

Original partial logs are untouched. The interrupted proposal never replaces the
active candidate. Infrastructure unknown is excluded from causal arm contrasts.
"""
import argparse
import json
from pathlib import Path
import research192_ablation as a

r,p,s,ROOT=a.refine,a.p,a.s,a.ROOT


def read_safe(path):
    try:return s.read(path)
    except (ValueError,OSError):return None


def recover(directory,arm,stream,strategy,seed):
    if (directory/'result.json').exists():raise ValueError('already_terminal')
    response=s.read(directory/'model_call/result.json')
    if response['status']!='response_received':raise ValueError('unexpected_interruption_state')
    initial=s.read(directory/'initial.json')
    _,jobs,protected,_=r.archived_baseline()
    baseline=r.binding.bound_measure(initial,jobs,protected)
    records=[]
    for depth in p.q.DEPTHS:
        for policy in p.q.POLICIES:
            for revision in ('before','after'):
                folder=directory/'native'/str(depth)/policy/revision
                value=read_safe(folder/'result.json')
                records.append(dict(folder=s.rel(folder),result=value,
                    status='preserved' if value else 'missing_or_truncated',
                    compile_record=read_safe(folder/'compile.json'),execute_record=read_safe(folder/'execute.json')))
    s.dump(directory/'recovery/native_integrity.json',records)
    s.dump(directory/'recovery/incident.json',dict(reason='D_disk_exhausted_during_native_execution_and_journal_write',
        original_runner_exception='OSError errno5 Input/output error while saving native/executions.json',
        original_partial_artifacts_preserved=True,model_redispatched=False,native_retries=0,
        complete_proposal_validation=False,causal_comparison_eligible=False,
        action='retain initial and continue only never-submitted sealed arms'))
    s.dump(directory/'decision.json',dict(accepted=False,regression=False,lost=[],new_false_positives=[],
        reason='infrastructure_unknown; no assertion regression attribution'))
    s.dump(directory/'terminal.json',initial)
    s.dump(directory/'frozen.json',dict(candidate_sha256=p.digest(initial),seed=seed,strategy=strategy,
        freeze_before_independent=True,independent_results_not_used=True,retained_due_to_infrastructure_unknown=True))
    compiles=list(directory.rglob('compile.json'))
    result=dict(strategy=strategy,arm=arm,search_stream=stream,seed=seed,parent_bug='axis_fifo_oversize_atomic_drop',
        status='infrastructure_interrupted',model_status=response['status'],candidate_generated=True,accepted=False,
        infrastructure_failure=True,causal_comparison_eligible=False,proposal_unknown=True,
        regression_proposals=0,accepted_regressions=0,final_detected=len(baseline['detected_ids']),
        final_targets=len(set(baseline['public_targets']+baseline['historical_targets'])),
        final_fp=len(baseline['false_positives']),final_fn=len(set(baseline['public_targets']+baseline['historical_targets'])-set(baseline['detected_ids'])),
        final_unknown=0,effective_rounds=0,model_calls=1,prompt_tokens=response['prompt_tokens'],completion_tokens=response['completion_tokens'],
        physical_native_compiles=len(compiles),logical_native_compiles=12,native_reuse_source=None,
        native_seconds=None,wall_seconds=None,command_cost_status='incomplete_records_due_to_disk_failure',
        independent_acceptance='pending',scope='same frozen original FIFO scope; infrastructure failure is not a mechanism failure')
    s.dump(directory/'result.json',result)
    return result


def resume(prepared,out):
    for name,digest in s.read(prepared/'seal.json').items():
        if s.sha(ROOT/name)!=digest:raise ValueError('sealed_input_changed:'+name)
    rows=s.read(out/'results.json')
    initial=s.read(prepared/'initial.json');protected=s.read(prepared/'protected.json');base=s.read(prepared/'base_request.json')
    seen={(v['seed'],v['arm']) for v in rows}
    for seed in a.SEEDS:
        for arm,(stream,strategy) in a.ARMS.items():
            directory=out/f'seed{seed}'/arm
            if (seed,arm) in seen:continue
            if directory.exists():
                result=recover(directory,arm,stream,strategy,seed)
            else:
                evidence=s.read(prepared/f'seed{seed}'/stream/'evidence.json')
                descriptors=s.read(prepared/f'seed{seed}'/stream/'descriptors.json')
                expected=s.read(prepared/'requests'/f'{seed}_{arm}.json')
                request,_=r.build_request(base,strategy,evidence,seed,initial)
                if request!=expected:raise ValueError('request_changed')
                result=r.run_arm(directory,strategy,seed,evidence,initial,protected,base,descriptors,workers=2)
                result.update(arm=arm,search_stream=stream)
            rows.append(result);seen.add((seed,arm));s.dump(out/'results.json',rows)
            print('ARM',json.dumps(result),flush=True)
    s.dump(out/'outcome.json',dict(status='completed',model_calls=sum(v['model_calls'] for v in rows),
        infrastructure_interrupted_arms=sum(v.get('infrastructure_failure',False) for v in rows),
        retries=0,original_failures_preserved=True))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();resume(args.prepared.resolve(),args.out.resolve())
