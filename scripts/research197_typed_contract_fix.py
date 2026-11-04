"""Unambiguous opt-in typed-only contract. Does not alter sealed R197 trials.

No model transport. Corrected requests require their own review and permission;
original T outcomes remain archived and are not silently replaced.
"""
import argparse
import copy
import json
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash
from research194_refinement import digest
from research197_refinement import runtime as original_runtime
from research197_cases import CaseAdapter


def runtime():
    core,runner=original_runtime('T');original=core.output_contract
    def contract(stage):
        value=copy.deepcopy(original(stage))
        if stage!='local':return value
        allowed=value['operations_allowed']
        value['operations']={k:v for k,v in value['operations'].items() if k in allowed}
        value['operations'].update(value.pop('r197_temporal_operations'))
        value['operations']['set_delay']=['assertion','field','expression','cycles:integer 0..32']
        value['operations']['set_window']=['assertion','field','expression','min_cycles:integer 0..32','max_cycles:integer 0..32','quantifier:any|all']
        value['schema']={'edits':'Array of 1..4 operation objects. Each object contains op plus exactly the fields listed for that operation in operations.','reason':'string'}
        value['rule']='Only names in operations_allowed are valid. No arbitrary field replacement. Choose every expression and numeric bound yourself. Existing labels and obligation mappings remain fixed.'
        return value
    core.output_contract=contract
    return core,runner


def prepare(prepared,out):
    prepared,out=Path(prepared),Path(out);p=read(prepared/'protocol.json')
    if file_hash(prepared/'protocol.json')!=read(prepared/'seal.json')['protocol_sha256']:raise ValueError('original_protocol_changed')
    out.mkdir(parents=True,exist_ok=False);entries=[]
    for e in p['entries']:
        if e.get('arm')!='T':continue
        state=read(e['state']);core,runner=runtime();adapter=CaseAdapter(e['case_id'])
        controller=runner.controller_from(adapter,e['strategy'],state['baseline'],1)
        request=core.build_request(adapter.case,controller,state['public_evidence'],e['seed'],0)
        old=read(e['request']);before=json.loads(old['messages'][-1]['content']);after=json.loads(request['messages'][-1]['content'])
        old_contract=before.pop('output_contract');new_contract=after.pop('output_contract')
        if before!=after or old['messages'][0]!=request['messages'][0]:raise ValueError('non_contract_information_changed')
        if 'replace_field' in json.dumps(new_contract) or set(new_contract['operations'])!=set(new_contract['operations_allowed']):raise ValueError('typed_contract_contradiction')
        dest=out/'requests'/e['id']/'request.preview.json';dump(dest,request)
        entries.append(dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],request=str(dest.resolve()),request_sha256=digest(request),
            original_state=e['state'],original_state_sha256=e['state_sha256'],original_request=e['request'],
            evidence_unchanged=True,only_output_contract_changed=True))
    data=dict(version='research197-typed-contract-fix',authorization='NOT AUTHORIZED; no external requests sent.',model_calls=0,
        original_protocol_sha256=file_hash(prepared/'protocol.json'),endpoint=p['endpoint'],model=p['model'],
        maximum_model_calls=len(entries),max_output_tokens=2048,timeout_seconds=300,workers=2,retries=0,max_rounds=1,
        source_bindings={**p['source_bindings'],str(Path(__file__).resolve()):file_hash(__file__)},entries=entries,
        scope='Six corrected T requests. Identical initial candidates, development evidence, seeds and gates; only conflicting output-contract examples removed. Original T results remain a distinct flawed-contract cohort. Not executed under the original 162-call grant.')
    dump(out/'protocol.json',data);dump(out/'seal.json',dict(protocol_sha256=file_hash(out/'protocol.json')))
    print(dict(corrected_requests=len(entries),model_calls=0,only_output_contract_changed=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepared',required=True,type=Path);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();prepare(args.prepared,args.out)
