"""Check compact requests against archived real development samples; no API calls."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import research17_model as base
from research22_model import Model, LocalModel
import research20_stall_runtime as stall


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--structured-local',action='store_true')
    parser.add_argument('--lexical-local',action='store_true');args=parser.parse_args()
    assert not args.lexical_local or args.structured_local
    out=args.out.resolve();out.mkdir(exist_ok=False,parents=True)
    source=base.ROOT/'deliverables/research21_closed_loop_20261018_r02/core/before/result.json'
    prior=base.read(source)
    current=base.read(base.ROOT/'deliverables/research20_closed_loop_20261018_r06/core/frozen_candidate.json')
    config=dict(options=dict(num_predict=1024,temperature=0,seed=2026101901),direct_property=True,call_timeout=180)
    model=Model(out,config);checks=[]
    with stall.installed():
        for targets in (['no_unsolicited_output','reset_cancellation'],['stall_stability']):
            payload=model._payload(current,targets[0],dict(requested_obligations=targets,actual_native_evidence=prior['feedback']),'qualification_no_call')
            task=json.loads(payload['messages'][2]['content'])['boundary_repair']
            for pair in task['actual_observations']:
                for side in ('fixed','mutant'):
                    p=Path(pair[side]['full_trace_provenance']['path']);samples=base.read(p)
                    expected=[next((s for s in samples if s['cycle']==cycle),None) for cycle in range(pair['cycle']-1,pair['cycle']+2)]
                    checks.append(dict(kind='exact_adjacent_samples',target=targets,scenario=pair['scenario'],side=side,
                        passed=expected==pair[side]['adjacent_samples'] and hashlib.sha256(p.read_bytes()).hexdigest()==pair[side]['full_trace_provenance']['sha256']))
            context=json.loads(payload['messages'][1]['content'])['rtl_and_common_contract']
            checks.append(dict(kind='full_rtl_and_unchanged_accepted_set',target=targets,
                passed=context['rtl_shared']==base.source.RTL.read_text() and task['accepted_properties']==[dict(property=a['property'],obligation=a['obligations']) for a in current['assertions']]))
            checks.append(dict(kind='nonempty_real_evidence',target=targets,passed=bool(task['actual_observations']),
                payload_bytes=len(json.dumps(payload).encode())))
            selected=LocalModel
            if args.structured_local:
                from research23_model import Model as StructuredModel
                selected=StructuredModel
            if args.lexical_local:
                from research24_model import Model as LexicalModel
                selected=LexicalModel
            local=object.__new__(selected);local.config=config
            request=dict(model='qwen2.5-coder:7b-instruct',options=config['options'],messages=[dict(role='system',content=''),
                dict(role='user',content=json.dumps(dict(rtl_shared=base.source.RTL.read_text(),signals=base.SIGNALS,reference_rtl=base.native.REFERENCE))),
                dict(role='user',content=json.dumps({}))])
            local_payload=local.transform_request(request,current,targets[0],dict(requested_obligations=targets,actual_native_evidence=prior['feedback']),'qualification_no_call')
            local_task=json.loads(local_payload['messages'][1]['content'])['boundary_repair']
            checks.append(dict(kind='local_same_evidence_no_remote_constructor',target=targets,
                passed=local_task['actual_observations']==task['actual_observations'] and local_task['accepted_properties']==task['accepted_properties']))
            if args.structured_local:
                schema=local_payload['format']
                prop_schema=schema['properties']['assertions']['items']['properties']['property']
                checks.append(dict(kind='schema_constrains_structure_not_predicates',target=targets,
                    passed=schema['required']==['reason','operation','assertions'] and
                    {k:v for k,v in prop_schema.items() if k!='pattern'}==dict(type='string',minLength=1,maxLength=1024)))
                if args.lexical_local:
                    pattern=prop_schema['pattern']
                    rejected_source=base.ROOT/'deliverables/research23_closed_loop_20261019_r01/core/v0/model_call/model_edit.json'
                    rejected=base.read(rejected_source)['assertions'][0]['property']
                    checks.append(dict(kind='lexical_existing_properties_allowed_actual_unknown_identifiers_excluded',target=targets,
                        passed=all(re.fullmatch(pattern,a['property']) is not None for a in current['assertions']) and re.fullmatch(pattern,rejected) is None,
                        rejected_source=str(rejected_source),rejected_source_sha256=hashlib.sha256(rejected_source.read_bytes()).hexdigest()))
                base.dump(out/(targets[0]+'_structured_local_request.json'),local_payload)
            base.dump(out/(targets[0]+'_request.json'),payload)
    for p in (Path(__file__),base.ROOT/'scripts/research22_model.py'):
        shutil.copy2(p,out/p.name)
    if args.structured_local:shutil.copy2(base.ROOT/'scripts/research23_model.py',out/'research23_model.py')
    if args.lexical_local:shutil.copy2(base.ROOT/'scripts/research24_model.py',out/'research24_model.py')
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,source=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),model_calls=0,native_calls=0,secret_contents_read=False,
        scope='Only archived real development observations and exact RTL; no simulated responses, no model request submitted.')
    base.dump(out/'qualification.json',result);print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
