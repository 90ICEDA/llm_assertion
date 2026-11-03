"""Replay actual model-owned text through replacement plumbing, no new SVA."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import research17_model as base
from research26_model import replace_one
from research26_cases import promoted_cases


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    source=base.ROOT/'deliverables/research25_closed_loop_20261020_r01'
    current=base.read(source/'core/frozen_candidate.json')
    actual=base.read(source/'core/v0/model_call/model_edit.json')
    edit=dict(**actual);edit.update(operation='replace_one',assertion_id='a3')
    before=copy.deepcopy(current);result=replace_one(edit,current)
    checks=[dict(name='same_actual_property_replacement_preserves_entire_set',passed=result==before),
        dict(name='input_not_mutated',passed=current==before)]
    from research20_report import direct_property_audit
    checks.append(dict(name='replacement_raw_property_audit_selects_actual_id',
        passed=direct_property_audit(edit,result,before)['passed']))
    altered=copy.deepcopy(result)
    altered['assertions'][3]['property']=before['assertions'][0]['property']
    checks.append(dict(name='replacement_raw_property_audit_rejects_changed_text',
        passed=direct_property_audit(edit,altered,before)['passed'] is False))
    invalid={**edit,'assertion_id':'missing'}
    try:replace_one(invalid,current);rejected=False
    except AssertionError:rejected=True
    checks.append(dict(name='unknown_replacement_id_rejected',passed=rejected))
    selected=promoted_cases(source)
    checks.append(dict(name='all_18_cases_promoted_without_stimulus_changes',passed=len(selected)==18 and
        all(c['split']=='development' and c['rows']==base.read(Path(c['provenance']['source_case']))['rows'] for c in selected)))
    from research26_model import replacement_request
    from research24_model import lexical_schema
    old_request=base.read(base.ROOT/'deliverables/research26_closed_loop_20261020_r02/core/v1/model_call/request.json')
    body=json.loads(old_request['messages'][1]['content'])
    expected=copy.deepcopy(body['boundary_repair']['actual_observations'])
    schema=lexical_schema()
    request=copy.deepcopy(old_request);request['format']=schema
    old_rejected=copy.deepcopy(body['boundary_repair']['previous_rejected_proposal'])
    focused=replacement_request(request,current,
        dict(previous_rejected_proposal=old_rejected),body,schema)
    focused_body=json.loads(focused['messages'][1]['content'])
    review=focused_body['final_temporal_review']
    checks.append(dict(name='focused_samples_exactly_match_actual_request',
        passed=focused_body['boundary_repair']['actual_observations']==expected))
    checks.append(dict(name='no_conflicting_add_instruction',
        passed='new complementary' not in focused_body['final_instruction'] and
            'Replace exactly ONE' in focused_body['final_instruction']))
    checks.append(dict(name='replacement_schema_has_unique_required_fields',
        passed=len(schema['required'])==len(set(schema['required'])) and schema['properties']['operation']['enum']==['replace_one']))
    checks.append(dict(name='rejected_text_omitted_with_exact_proposal_hash',
        passed='previous_rejected_proposal' not in focused_body['boundary_repair']
            and review['rejected_proposal_sha256']==hashlib.sha256(json.dumps(old_rejected,sort_keys=True).encode()).hexdigest()))
    checks.append(dict(name='counter_projection_preserves_actual_values',
        passed=all(c['actual_fault_counter_samples']==[
            {k:s[k] for k in ('cycle','rst','ref_count','mvalid','mready') if k in s} if s else None
            for s in o['mutant']['adjacent_samples']] for c,o in zip(review['counter_samples'],expected))
            and len(review['counter_samples'])==len(expected)))
    base.dump(out/'qualified_request_projection.json',focused)
    base.dump(out/'promoted_cases.json',selected)
    for path in (Path(__file__),base.ROOT/'scripts/research26_model.py',base.ROOT/'scripts/research26_cases.py'):
        shutil.copy2(path,out/path.name)
    record=dict(passed=all(c['passed'] for c in checks),checks=checks,
        source_candidate_sha256=hashlib.sha256((source/'core/frozen_candidate.json').read_bytes()).hexdigest(),
        model_calls=0,compile_calls=0,native_execution_calls=0,formal_calls=0,
        scope='Plumbing only: same previously generated property reinserted; no new generated or hand-authored repair candidate.')
    base.dump(out/'qualification.json',record);print(json.dumps(record))
    if not record['passed']:raise SystemExit(1)


if __name__=='__main__':main()
