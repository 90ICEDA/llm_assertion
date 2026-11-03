"""Audit actual request and promoted development inputs; no generation."""
import argparse
import hashlib
import json
from pathlib import Path
import research17_model as base
from research21_report import portable, prompt_evidence_audit


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    run=args.run.resolve();out=args.out.resolve()
    assert base.ROOT in run.parents and base.ROOT in out.parents
    out.mkdir(parents=True,exist_ok=False)
    request=base.read(run/'core/v0/model_call/request.json')
    body=json.loads(request['messages'][1]['content'])
    current=base.read(run/'shared_initial.json')
    task=body['fresh_obligation_synthesis']
    text='\n'.join(m['content'] for m in request['messages'])
    plan=base.read(run/'development_plan.json')
    promoted=[c for c in plan if c['source']=='published_test_promoted_after_observed_failure']
    prompt=prompt_evidence_audit(run)
    checks=dict(
        raw_RTL_present=body['rtl_and_common_contract']['rtl_shared']==(run/'axis_fifo.v').read_text(),
        no_prior_property_strings=all(a['property'] not in text for a in current['assertions']),
        original_set_hash_matches=task['old_set_sha256']==hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest(),
        requested_slot_exists=task['assertion_id'] in [a['id'] for a in current['assertions']],
        native_source_observations_exact=prompt['faithful'],
        both_current_queue_boundaries_observed={
            p['faulty_samples'][-1]['ref_count']>0 for p in task['observations']}=={False,True},
        all_90_promoted_cases_unchanged=len(promoted)==90 and all(
            c['rows']==base.read(portable(c['provenance']['source_case']))['rows']
            and c['provenance']['source_sha256']==hashlib.sha256(portable(c['provenance']['source_case']).read_bytes()).hexdigest()
            for c in promoted),
        all_promoted_cases_are_development=all(c['split']=='development' for c in promoted),
        unique_case_identities=len({c['id'] for c in plan})==len(plan))
    base.dump(out/'prompt_evidence.json',prompt)
    result=dict(passed=all(checks.values()),checks=checks,model_calls=0,native_calls=0,
        request_sha256=hashlib.sha256((run/'core/v0/model_call/request.json').read_bytes()).hexdigest(),
        scope='Actual request, development provenance and exact samples only; not an assertion correctness result.')
    base.dump(out/'qualification.json',result)
    (out/'audit_script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
