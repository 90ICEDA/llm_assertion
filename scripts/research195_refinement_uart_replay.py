"""Replay an archived response through safe request/localization/native gate/freeze.

This is an integration qualification, not a new LLM trial or historical rerun.
The archived response originated from a different request, recorded explicitly.
"""
import argparse
import copy
import json
from pathlib import Path
from research195_refinement_adapter import runtime,ArchivedResponseBackend
from research194_refinement_safe_localization import safe_localize


def run(root,out):
    core,runner=runtime('F')
    old=root/'deliverables/research194_campaign_execute_20261103_r01/base/uart/19419'
    broken=old/'S2_R1/refinement'
    before=runner.read(broken/'round02/current_measurement.json')
    context=json.loads(runner.read(broken/'round02/request.preview.json')['messages'][-1]['content'])
    candidate=context['current_assertions'];queries=runner.read(broken/'trajectory_queries.json')
    adapter=runner.CaseAdapter('uart');adapter.case['initial']=copy.deepcopy(candidate)
    class Session:
        strategy='archived_query_replay'
        def acquire(self,*args,**kwargs):
            return dict(queries=queries,measurement=before,task_id='R195/UART/archived-null-obligation-replay',
                cost=dict(native_compile_attempts=0,native_execution_attempts=0,physical_native_jobs=0,
                    provenance='reused_original_native_measurement'))
    evidence=runner.model_evidence(before);audit=safe_localize(candidate,evidence)
    if not audit['unmapped_localizations']:raise ValueError('missing_real_null_obligation_fixture')
    archive=old.parent/'19407/S1_R1/refinement/round01/model_edit.json'
    loaded_sources={str(p):runner.file_hash(p) for p in (Path(__file__),Path(__file__).with_name('research195_refinement_adapter.py'),
        Path(__file__).with_name('research194_refinement_safe_localization.py'))}
    result=runner.run_trajectory(adapter,'R3',19507,out,before,queries,Session(),
        ArchivedResponseBackend(archive),max_rounds=1)
    runner.dump(out/'safe_localization_audit.json',audit)
    runner.dump(out/'qualification.json',dict(new_model_calls=0,original_evidence_unchanged=audit['evidence']==evidence,
        unmapped_preserved=len(audit['unmapped_localizations']),proposal_native_executed=(out/'round01/proposal_native/measurement.json').exists(),
        gate_and_freeze_reached=result['status']=='frozen',archived_source_request_differs=True,
        source_bindings_at_start=loaded_sources,archived_response_structural_contract='Same labels/obligations; only conjunct ordering differs, not a claimed semantic repair.',
        claim='Integration qualification only. Native replay is new; response is archival and not a generated R195 model result.',outcome=result))
    print(json.dumps(dict(status=result['status'],model_calls=result['actual_model_calls'],accepted=result['accepted_rounds'],unmapped=len(audit['unmapped_localizations']))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();run(args.root.resolve(),args.out)
