"""Read-only provenance/budget audit of all sixteen actual R/A model calls."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENDPOINT='https://api.highwayapi.ai/openai/chat/completions'
MODEL='deepseek/deepseek-v3-0324'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rel(path):return Path(path).resolve().relative_to(ROOT).as_posix()


def audit(out):
    families={
        'R':(ROOT/'deliverables/research192_refinement_prepare_20261103_r02',ROOT/'deliverables/research192_refinement_20261103_r01'),
        'A':(ROOT/'deliverables/research192_ablation_prepare_20261103_r01',ROOT/'deliverables/research192_ablation_20261103_r01')}
    records=[];bindings={};issues=[];checks=[]
    def check(name,condition):checks.append(dict(name=name,passed=bool(condition)))
    for family,(prep,run) in families.items():
        seal=read(prep/'seal.json');bindings[rel(prep/'seal.json')]=sha(prep/'seal.json')
        for seed in (19207,19219):
            for index in range(4):
                arm=family+str(index);folder=run/f'seed{seed}'/arm
                expected=prep/f'seed{seed}'/arm/'request.preview.json' if family=='R' else prep/'requests'/f'{seed}_{arm}.json'
                actual=folder/'model_call/request.json'
                local=folder/'request.preview.json'
                request=read(actual);sealed=read(expected)
                result=read(folder/'model_call/result.json')
                generation=read(folder/'model_call/generation_config.json')
                attempt=read(folder/'model_call/attempt.json')
                summary=read(folder/'transport/remote_transport_config.json')
                terminal=read(folder/'result.json')
                raw=read(folder/'model_call/response.assembled.json')
                usage=raw['service_done']['usage']
                identifier=f'{family}/{seed}/{arm}'
                key=rel(expected)
                check(identifier+' sealed request hash',key in seal and sha(expected)==seal[key])
                check(identifier+' actual request identical to sealed',request==sealed==read(local))
                check(identifier+' fixed sampling',
                    (request['model'],request['seed'],request['temperature'],request['max_tokens'])==(MODEL,seed,0.2,1024))
                check(identifier+' actual endpoint/model',
                    generation['endpoint']==result['endpoint']==summary['endpoint']==ENDPOINT
                    and result['model']==generation['model']==MODEL
                    and result['actual_server_model']==MODEL)
                check(identifier+' effective deadline300',generation['timeout_seconds']==attempt['timeout_seconds']==300)
                check(identifier+' no retry',attempt['retries']==result['retries']==0)
                check(identifier+' one attempt',len(list((folder/'model_call').glob('attempt.json')))==1)
                check(identifier+' actual provider usage',usage['prompt_tokens']==result['prompt_tokens']
                    and usage['completion_tokens']==result['completion_tokens']
                    and result['prompt_tokens']==terminal['prompt_tokens']
                    and result['completion_tokens']==terminal['completion_tokens'])
                body=json.loads(request['messages'][1]['content'])
                is_infra=bool(terminal.get('infrastructure_failure'))
                if is_infra:
                    check(identifier+' infrastructure is not regression',
                        not terminal['regression_proposals'] and not terminal['accepted_regressions']
                        and not terminal['accepted'] and terminal.get('causal_comparison_eligible') is False)
                if summary['timeout_seconds']!=generation['timeout_seconds']:
                    issues.append(dict(arm=identifier,type='informational_timeout_metadata_stale',
                        transport_summary_seconds=summary['timeout_seconds'],
                        actual_attempt_and_generation_seconds=generation['timeout_seconds'],
                        explanation='Inherited transport constructor writes min(180,config_timeout), but actual call uses min(300,config_timeout,remaining). Attempt and generation records agree on the actual300s cap. Original metadata is not rewritten.'))
                records.append(dict(family=family,seed=seed,arm=arm,source=rel(folder),
                    sealed_request=key,sealed_sha256=sha(expected),actual_request_sha256=sha(actual),
                    semantic_request_exact_match=request==sealed,
                    endpoint=result['endpoint'],requested_model=request['model'],actual_model=result['actual_server_model'],
                    max_output_tokens=request['max_tokens'],temperature=request['temperature'],
                    actual_timeout_seconds=generation['timeout_seconds'],summary_timeout_seconds=summary['timeout_seconds'],
                    retries=result['retries'],model_calls=1,provider_response_id=result['response_id'],
                    prompt_tokens=result['prompt_tokens'],completion_tokens=result['completion_tokens'],
                    model_wall_seconds=result['wall_seconds'],transport_status=result['status'],
                    candidate_status=result['candidate_status'],candidate_error=result.get('candidate_error'),
                    accepted=terminal['accepted'],infrastructure_failure=is_infra,
                    initial_candidate_origin='research188 archived engineered partial candidate; no new initial-generation call',
                    observations_sha256=hashlib.sha256(json.dumps(body['development_observations'],sort_keys=True).encode()).hexdigest()))
                for path in (expected,actual,folder/'model_call/result.json',folder/'model_call/generation_config.json',
                    folder/'model_call/attempt.json',folder/'model_call/response.assembled.json',folder/'result.json'):
                    bindings[rel(path)]=sha(path)
        attempts=list(run.glob('seed*/*/model_call/attempt.json'))
        check(family+' exact8 attempts',len(attempts)==8)
    check('exact16 distinct provider responses',len(records)==len({r['provider_response_id'] for r in records})==16)
    for seed in (19207,19219):
        rrows=[v for v in records if v['family']=='R' and v['seed']==seed]
        check('R same raw observations '+str(seed),len({x['observations_sha256'] for x in rrows})==1)
        arows={v['arm']:v for v in records if v['family']=='A' and v['seed']==seed}
        check('A0/A2 same raw observations '+str(seed),arows['A0']['observations_sha256']==arows['A2']['observations_sha256'])
        check('A1/A3 same raw observations '+str(seed),arows['A1']['observations_sha256']==arows['A3']['observations_sha256'])
    arun=families['A'][1]
    a0=arun/'seed19219/A0';candidate=read(a0/'model_call/candidate.json')
    measurement=read(a0/'measurement.json');acquired=read(a0/'acquired_measurement.json')
    targets=set(measurement['public_targets']+measurement['historical_targets'])
    a0_diagnosis=dict(arm='A0',seed=19219,classification='confirmed_missed_ready_first_targets',
        actual_native_execution=True,ordinary_accept=measurement['ordinary_accept'],
        historical_accept=measurement['historical_accept'],false_positives=measurement['false_positives'],
        critical_unknown=measurement['critical_unknown'],lost_history=measurement['lost'],
        full_gate_detected=measurement['detected_ids'],
        full_gate_missing=sorted(targets-set(measurement['detected_ids'])),
        full_gate_untriggered=sorted(targets-set(measurement['triggered_ids'])),
        acquired_missing=sorted(set(acquired['public_targets']+acquired['historical_targets'])-set(acquired['detected_ids'])),
        candidates=candidate,explanation='Every proposed antecedent retains !m_axis_tready. Native markers confirm no trigger on ready-first target presentations. Stalled-first historical targets remain protected; no false alarms or unknown. Ordinary/current gate rejects actual misses, so this is failed improvement rather than regression of prior protection.')
    check('A0 ready misses confirmed without unknown',not measurement['ordinary_accept']
        and not measurement['critical_unknown'] and not measurement['false_positives']
        and not measurement['lost'] and bool(a0_diagnosis['full_gate_missing']))
    a3=arun/'seed19219/A3';edit=read(a3/'model_call/model_edit.json')
    initial=read(a3/'initial.json');findings=read(a3/'localization.json')
    allowed={(x['assertion'],x['field']) for x in findings}
    invalid=[]
    for item in edit['edits']:
        key=(item['assertion'],item['field'])
        original=next(a for a in initial if a['label']==item['assertion'])
        if key not in allowed:
            invalid.append(dict(**item,unchanged_value=item['value']==original[item['field']],
                actual_reason='field_not_localized; not a duplicate field'))
    a3_diagnosis=dict(arm='A3',seed=19219,classification='constrained_edit_interface_rejection',
        exact_adapter_error=read(a3/'model_call/result.json')['candidate_error'],
        localized_fields=sorted(allowed),rejected_operations=invalid,
        raw_model_edit=edit,actual_native_execution=False,
        explanation='The first antecedent replacement is allowed. A second replace_field echoes the unchanged consequent, which is not localized. The frozen adapter rejects the complete patch with its combined unlocalized_or_duplicate_field error. It is specifically unlocalized, not duplicate. No candidate or native proposal waveform exists; no post-hoc no-op filtering was performed.')
    check('A3 specific nonlocalized unchanged consequent',len(invalid)==1
        and invalid[0]['field']=='consequent' and invalid[0]['unchanged_value']
        and not (a3/'model_call/candidate.json').exists() and not (a3/'native').exists())
    for folder in (a0,a3):
        for name in ('measurement.json','acquired_measurement.json','localization.json','model_call/model_edit.json'):
            if (folder/name).exists():bindings[rel(folder/name)]=sha(folder/name)
    totals={family:dict(model_calls=sum(x['model_calls'] for x in records if x['family']==family),
        prompt_tokens=sum(x['prompt_tokens'] for x in records if x['family']==family),
        completion_tokens=sum(x['completion_tokens'] for x in records if x['family']==family)) for family in families}
    totals['all']=dict(model_calls=16,prompt_tokens=sum(x['prompt_tokens'] for x in records),
        completion_tokens=sum(x['completion_tokens'] for x in records))
    for value in totals.values():value['total_tokens']=value['prompt_tokens']+value['completion_tokens']
    value=dict(audit_status='passed' if all(x['passed'] for x in checks) else 'failed',
        scope='Read-only audit, zero new model/native calls, original artifacts and sealed code unchanged.',
        checks=checks,totals=totals,requests=records,metadata_inconsistencies=issues,
        effective_timeout_interpretation='300seconds in per-attempt and effective generation records; constructor summary incorrectly says180seconds and is retained as an explicit provenance issue.',
        A0_rejection=a0_diagnosis,A3_rejection=a3_diagnosis,
        infrastructure_interrupted_arms=[dict(family=x['family'],seed=x['seed'],arm=x['arm']) for x in records if x['infrastructure_failure']],
        causal_warning='R3 seed19207 and A2 seed19207 were interrupted by disk exhaustion. They are not algorithm regressions and the corresponding paired seed cannot support a complete causal contrast.',
        source_bindings=bindings,script_sha256=sha(__file__))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(audit_status=value['audit_status'],checks=len(checks),failed=[x for x in checks if not x['passed']],totals=totals,metadata_timeout_inconsistencies=len(issues))),flush=True)
    if value['audit_status']!='passed':raise ValueError('audit_failed')


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--out',required=True,type=Path)
    args=cli.parse_args();audit(args.out.resolve())
