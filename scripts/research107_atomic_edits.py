"""Alternative generation representation: atomic edits of the OP assertion set.

No action is selected locally. Predicates/timing come from the model or unchanged
existing model components. The original textual frontend validates the result.
"""
import copy
import json
import research104_temporal_recovery as previous

p,x=previous.p,previous.x
FIELDS=previous.temporal.fmt.FIELDS


def adapt(value,current,fixed):
    if type(value) is not dict or set(value)!={'operation','reason','edits'}:raise ValueError('edit_top_fields')
    if value['operation']!='edit_op_set' or type(value['reason']) is not str:raise ValueError('edit_operation_or_reason')
    if type(value['edits']) is not list or len(value['edits'])>6:raise ValueError('edit_list_limit')
    components={a['id']:copy.deepcopy(a) for a in current['assertions'] if a['obligations']==['op_bit28_illegal']}
    if len(components)!=len(current['assertions'])-1:raise ValueError('unexpected_components')
    touched=set();replacements={};removed=set();added=[];actions=[]
    # Validate everything before rendering anything. Targets always refer to the
    # supplied immutable input snapshot, not indices shifted by earlier removals.
    for edit in value['edits']:
        if type(edit) is not dict:raise ValueError('edit_not_object')
        action=edit.get('action')
        expected={'action','assertion'} if action=='add' else ({'action','op_id','assertion'} if action=='replace' else {'action','op_id'})
        if action not in ('keep','remove','replace','add') or set(edit)!=expected:raise ValueError('action_fields')
        if action!='add':
            target=edit['op_id']
            if type(target) is not str or target not in components or target in touched:raise ValueError('unknown_or_duplicate_op_id')
            touched.add(target)
            if action=='remove':removed.add(target)
            elif action=='replace':replacements[target]=copy.deepcopy(edit['assertion'])
        else:added.append(copy.deepcopy(edit['assertion']))
        if action in ('replace','add'):
            assertion=edit['assertion']
            if type(assertion) is not dict or set(assertion)!=set(FIELDS):raise ValueError('assertion_fields')
        actions.append(copy.deepcopy(edit))
    assertions=[replacements.get(key,{k:a[k] for k in FIELDS}) for key,a in components.items() if key not in removed]+added
    full=dict(operation='replace_op',reason=value['reason'],assertions=assertions)
    candidate,mapping=p.prior.p.TEXT_ADAPT(full,fixed)
    assert candidate['assertions'][0]==fixed['assertions'][0]
    assert all(all(a[k]==b[k] for k in FIELDS) for a,b in zip(assertions,candidate['assertions'][1:]))
    return candidate,dict(source='model_selected_atomic_edit',actions=actions,
        inherited_ids=[k for k in components if k not in removed and k not in replacements],
        expanded_model_edit=full,native_label_mapping=mapping)


def request(current,records,folder,arm,iteration,diagnostic=None):
    if arm not in ('C','E'):raise ValueError('unknown_arm')
    req=previous.temporal.request(current,records,folder,iteration,diagnostic)
    body=json.loads(req['messages'][1]['content'])
    body['current_op_ids']=[a['id'] for a in current['assertions'] if a['obligations']==['op_bit28_illegal']]
    body['component_binding']='current_op_ids and current_op are aligned by position. They name this request snapshot only. BRANCH is immutable. Choose changes yourself from actual development evidence.'
    # Common facts/system/task/diagnostics are the same at matched states. Only
    # the output representation differs. No suggested edits or successful SVA.
    if arm=='E':
        body['output_contract']={
            'top_level_fields':['operation','reason','edits'],'operation':'edit_op_set',
            'reason':'string','edits':'array of zero to six edits; omitted components are kept unchanged',
            'actions':{
                'keep':{'fields':['action','op_id'],'effect':'keep that current OP component'},
                'remove':{'fields':['action','op_id'],'effect':'remove that current OP component'},
                'replace':{'fields':['action','op_id','assertion'],'effect':'replace that current OP component with your complete assertion'},
                'add':{'fields':['action','assertion'],'effect':'append your complete assertion'}},
            'assertion_fields':list(FIELDS),'assertion_types':{'antecedent':'SystemVerilog expression string','consequent':'SystemVerilog expression string','timing':['same_sample','next_sample'],'obligations':['op_bit28_illegal']},
            'constraints':'Each existing op_id may appear once; no BRANCH edit; final OP set size1..3. Unknown/extra fields rejected. No suggested action or target. Native checks, repeat rejection and legal/target obligations unchanged.'}
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    req['seed']=10807+iteration
    return req
