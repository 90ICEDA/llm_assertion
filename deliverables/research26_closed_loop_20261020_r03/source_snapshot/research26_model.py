"""Model-owned replacement of one property in a full accepted assertion set."""
import copy
import json
import research17_model as base
from research24_model import Model as PreviousModel
from research22_model import Model as PreviousRemoteModel
from research23_model import edit_schema


def replace_one(value, current):
    assert set(value)=={'operation','assertion_id','assertions','reason'},'replacement_schema'
    assert value['operation']=='replace_one' and len(value['assertions'])==1
    ids=[a['id'] for a in current['assertions']]
    assert value['assertion_id'] in ids,'replacement_unknown_id'
    item=value['assertions'][0]
    assert set(item)=={'property','obligation'}
    props=copy.deepcopy(current['assertions'])
    props[ids.index(value['assertion_id'])]=dict(property=item['property'],
        obligations=item['obligation'],reason=value['reason'])
    return base.native.normalize_candidate(dict(assertions=props,syntax_profile='qualified_sampled_multi_v2'))


class Model(PreviousModel):
    def __init__(self,out,config):
        super().__init__(out,config)
        self.assemble=replace_one

    def transform_request(self,request,current,target,feedback,phase):
        request=super().transform_request(request,current,target,feedback,phase)
        return replacement_request(request,current,feedback,
            json.loads(request['messages'][1]['content']),request['format'])


def replacement_request(request,current,feedback,body,schema):
    """Present exact sampled contrasts at the end; never supply a predicate."""
    task=body['boundary_repair']
    schema['properties']['operation']['enum']=['replace_one']
    schema['required'].insert(1,'assertion_id')
    schema['properties']['assertion_id']=dict(type='string',enum=[a['id'] for a in current['assertions']])
    targets=task['requested_obligations']
    schema['properties']['assertions']['items']['properties']['obligation']=dict(
        type='array',minItems=len(targets),maxItems=len(targets),uniqueItems=True,
        items=dict(type='string',enum=targets))
    task['accepted_properties']=[dict(assertion_id=a['id'],property=a['property'],obligation=a['obligations']) for a in current['assertions']]
    task['operation']='Replace exactly ONE existing property chosen by assertion_id. The other properties are retained byte-for-byte by the assembler. The full set is replayed before acceptance.'
    task['response_schema']=schema
    body['output_schema']=schema
    # Remove the inherited ADD instruction; it contradicted replace_one.
    body['final_instruction']=task['operation']+' '+task['boundary_semantics']
    observations=[]
    for card in task['actual_observations']:
        observations.append(dict(scenario=card['scenario'],cycle=card['cycle'],
            independent_judgment=copy.deepcopy(card['target_evidence']),
            actual_fault_samples=copy.deepcopy(card['mutant']['adjacent_samples']),
            actual_correct_samples=copy.deepcopy(card['fixed']['adjacent_samples'])))
    body['final_temporal_review']=dict(observations=observations,
        accepted_properties=task['accepted_properties'],
        rejected_proposal=feedback.get('previous_rejected_proposal'),
        rejection_kinds=task['decision_reasons'],
        instructions='Read the exact old expression, including any $past. Numerically compare the previous and current samples around reset. The reference queue already tracks accepted and uncancelled transactions; do not reconstruct uniqueness or constrain unrelated payload history. Decide which sampled state the obligation requires. Do not repeat the rejected expression. Return a minimal replacement and a brief reason tied to these actual values.')
    request['messages'][0]['content']=(
        'Repair one existing native SVA using the real violating samples. Return exactly the JSON schema. '
        'Choose the assertion_id to replace, and generate its complete new implication expression. '
        'All other properties stay unchanged. Explain why the chosen old property misses these samples. '
        'No predicate is supplied or corrected for you. Never use the required outcome as an assumption. '
        'Use the current pre-NBA sampled meanings of the provided signals. '
        'ref_count is the independent count of accepted, uncancelled inputs still awaiting output at this sample. '
        'Do not introduce new signals or quantifiers. '+task['boundary_semantics']+
        ' Do not repeat a previously rejected proposal; use its actual replay failures. '
        'Your final temporal review repeats the exact observed samples after the RTL for clarity.')
    request['messages'][1]['content']=json.dumps(body)
    return request


class RemoteModel(PreviousRemoteModel):
    """Same model-owned replacement through the existing authorized relay."""
    def __init__(self,out,config):
        super().__init__(out,config)
        self.assemble=replace_one

    def transform_request(self,request,current,target,feedback,phase):
        request=super().transform_request(request,current,target,feedback,phase)
        common=json.loads(request['messages'][1]['content'])
        task=json.loads(request['messages'][2]['content'])
        request['messages']=[request['messages'][0],dict(role='user',content='')]
        # This schema is prompt text; the remote endpoint only requests a JSON
        # object. Do not claim backend lexical-grammar enforcement remotely.
        return replacement_request(request,current,feedback,{**common,**task},edit_schema())
