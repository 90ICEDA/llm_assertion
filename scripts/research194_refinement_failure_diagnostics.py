"""Read-only deterministic replay of local diagnostics, never model/native RTL.

Reproduced traceback is labeled separately from the original outer exception.
"""
import argparse
import hashlib
from pathlib import Path
import traceback
from research194_refinement_posthoc import read,dump,request_context
import research194_refinement as refinement
from research194_refinement_safe_localization import safe_localize


def analyze(campaign,out):
    campaign=Path(campaign);rows=[]
    for folder in sorted((campaign/'base').glob('*/*/*/refinement')):
        outcome=read(folder/'outcome.json',{})
        if outcome.get('error_type')!='TypeError':continue
        incomplete=[p for p in sorted(folder.glob('round*')) if (p/'request.preview.json').is_file() and not (p/'model_call'/'attempt.json').exists()]
        for rd in incomplete:
            _,context=request_context(rd/'model_call')
            candidates=context.get('current_assertions',[]);evidence=context.get('development_observations',[])
            nulls=[e for e in evidence if e.get('obligation') is None and e.get('status')=='confirmed'
                and e.get('label')=='legal' and any(a.get('failure') for a in e.get('assertions',[]))]
            exception=None;stack=None
            try:refinement.localize(candidates,evidence)
            except Exception as exc:
                exception=dict(type=type(exc).__name__,message=str(exc));stack=traceback.format_exc()
            safe=safe_localize(candidates,evidence)
            results=[read(p) for p in folder.glob('round*/model_call/result.json')]
            rows.append(dict(folder=str(folder),round=rd.name,original_outer_exception=dict(type=outcome['error_type'],message=outcome.get('error')),
                diagnosis='localization_diagnostic_nullable_obligation_type_error' if nulls and exception and exception['type']=='TypeError' else 'unresolved',
                input_null_obligation_legal_alarms=nulls,
                candidate_sha256=refinement.digest(candidates),request_context_sha256=refinement.digest(context),
                sealed_localizer_source_sha256=hashlib.sha256(Path(refinement.__file__).read_bytes()).hexdigest(),
                replayed_pure_function_exception=exception,replayed_pure_function_traceback=stack,
                isolated_adapter_replay=dict(status=safe['status'],original_evidence_identical=safe['evidence']==evidence,
                    unmapped_localizations=safe['unmapped_localizations'],
                    evidence_records_dropped=safe['evidence_records_dropped'],oracle_labels_modified=safe['oracle_labels_modified'],
                    actionable_findings_count=len(safe['actionable_findings']),
                    current_campaign_imports_adapter=False,not_a_model_or_native_experiment=True),
                traceback_provenance='posthoc pure-function replay of exact persisted request data; original outer wrapper recorded error type/message only',
                stage='After next query/current-history measurement and request construction, before diagnostic completes and before backend submission.',
                classification='local_algorithm_diagnostic_implementation_failure_not_RTL_infrastructure_or_model_schema_or_output_truncation',
                round_model_attempt_exists=False,retained_frozen_sha256=outcome.get('frozen_sha256'),
                actual_model_calls=sum(x.get('model_calls',0) for x in results if x),
                known_tokens=sum((x.get('prompt_tokens') or 0)+(x.get('completion_tokens') or 0) for x in results if x),
                unknown_usage_calls=sum(x.get('prompt_tokens') is None or x.get('completion_tokens') is None for x in results if x),
                new_model_calls=0,new_native_executions=0,sealed_files_modified=False))
    dump(Path(out)/'outer_exception_diagnostics.json',rows)
    print([{k:r[k] for k in ('folder','diagnosis','actual_model_calls','known_tokens','unknown_usage_calls')} for r in rows])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.campaign,a.out)
