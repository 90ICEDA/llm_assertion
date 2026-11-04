"""Metadata-only compatibility for frozen R195 independent query generation.

The sealed generator omitted semantic_key required by the existing evaluator.
Only this derived key is added; old plan id/rows and all frozen candidates are
checked unchanged. No independent grades are read, no model transport occurs.
"""
import argparse
import copy
from pathlib import Path
import traceback
from research195_refinement_adapter import clone
import research194_refinement_runner as common


def run(prepared,execution,failed,out,audit):
    failed=Path(failed);out=Path(out);audit=Path(audit)
    if audit.exists() or out.exists():raise ValueError('compatibility_outputs_must_be_new')
    old_plan=common.read(failed/'plan.json')
    # Read only physical execution metadata, never result projections/grades.
    jobs=[]
    for result_path in sorted(failed.glob('*/native/q*/*/result.json')):
        result=common.read(result_path)
        jobs.append(dict(path=str(result_path),sha256=common.file_hash(result_path),
            compile_status=result.get('compile_status'),execution_status=result.get('execution_status'),
            compile_seconds=result.get('compile',{}).get('wall_seconds',0),
            execution_seconds=result.get('execute',{}).get('wall_seconds',0)))
    incident=dict(error_type='KeyError',error="'semantic_key'",fixture='delay',
        original_exec_session=67979,original_failure_stage='research194_cases.evaluate: legal_unbound_alarm evidence identity construction after first completed correct native job',
        failed_directory=str(failed),failed_plan_sha256=common.file_hash(failed/'plan.json'),jobs=jobs,
        completed_compiles=sum(j['compile_status']=='passed' for j in jobs),
        completed_executions=sum(j['execution_status']=='completed' for j in jobs),
        physical_seconds=sum(j['compile_seconds']+j['execution_seconds'] for j in jobs),
        interpretation='Independent-query metadata interface failure, not a model-generation or RTL semantic failure. Original records retained.',
        new_model_calls=0)
    common.dump(audit/'original_incident.json',incident)
    private=clone('research195_refinement_independent');original_generate=private.generate
    changes=[]
    def generate(case_id,seed):
        query=original_generate(case_id,seed)
        matches=[old for group in old_plan['queries'].values() for old in group if old['id']==query['id']]
        if not matches or any(old!=query for old in matches):raise ValueError('query_changed_from_failed_registered_plan')
        updated=copy.deepcopy(query);updated['semantic_key']=common.r.digest(query['rows'])
        if {k:v for k,v in updated.items() if k!='semantic_key'}!=query:raise ValueError('non_metadata_patch')
        changes.append(dict(query_id=query['id'],seed=seed,rows_sha256=common.r.digest(query['rows']),
            original_query_sha256=common.r.digest(query),added_fields={'semantic_key':updated['semantic_key']},
            rows_identical=True,id_identical=True,all_original_fields_identical=True))
        common.dump(audit/'query_metadata_diff.json',changes)
        return updated
    private.generate=generate
    common.dump(audit/'compatibility_protocol.json',dict(source=str(Path(__file__)),source_sha256=common.file_hash(__file__),
        sealed_generator=private.__file__,sealed_generator_sha256=common.file_hash(private.__file__),
        allowed_change='semantic_key := canonical digest(query.rows)',
        changed_candidates=False,changed_oracle=False,changed_seeds=False,changed_thresholds=False,
        selected_inputs_using_grades=False,read_old_grades=False,new_model_calls=0))
    try:private.run(prepared,execution,out)
    except Exception as exc:
        common.dump(audit/'outcome.json',dict(status='failed',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc(),new_model_calls=0))
        raise
    common.dump(audit/'outcome.json',dict(status='completed',query_constructions=len(changes),
        all_original_query_fields_identical=all(c['all_original_fields_identical'] for c in changes),
        new_model_calls=0,original_incident_native_jobs=len(jobs),independent_outcome=str(out/'outcome.json')))
    print(dict(status='completed',metadata_only=True,original_native_jobs=len(jobs)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','execution','failed','out','audit'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.execution,a.failed,a.out,a.audit)
