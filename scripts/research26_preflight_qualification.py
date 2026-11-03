"""Regression of an actual preflight failure; no model or simulated response."""
import argparse
import json
from pathlib import Path
import shutil
from unittest.mock import patch
import research24_model as subject
import research17_model as base


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    source=base.ROOT/'deliverables/research26_closed_loop_20261020_r05/core/v0/context_preflight/decision.json'
    actual=base.read(source)
    assert actual['status']=='context_budget_rejected_before_generation' and actual['model_calls']==0
    log=out/'qualification_only.log';log.write_text('No model service involved.\n')
    model=object.__new__(subject.Model)
    model.config={'local_service_log':str(log)};model.out=out;model.calls=[]
    folder=out/'v0/model_call'
    # Stub only the already-recorded preflight return, never a model response.
    with patch.object(subject.PreviousModel,'call',return_value=(dict(actual),None)):
        result,candidate=model.call(folder)
    checks=dict(candidate_absent=candidate is None,
        actual_preflight_status_preserved=result['status']==actual['status'],
        generation_directory_not_created=not folder.exists(),
        no_generation_counted=result['model_calls']==0 and not model.calls,
        backend_skip_recorded=base.read(out/'v0/backend_preflight_skip.json')['status']=='not_applicable_no_generation_attempt')
    record=dict(passed=all(checks.values()),checks=checks,source=str(source),
        model_calls=0,native_compile_calls=0,native_execute_calls=0,formal_calls=0,
        scope='Failure-path plumbing regression over an actual saved preflight decision, not model generation or SVA success.')
    base.dump(out/'qualification.json',record)
    shutil.copy2(__file__,out/'script.py');shutil.copy2(subject.__file__,out/'research24_model.py')
    print(json.dumps(record))
    assert record['passed']


if __name__=='__main__':
    main()
