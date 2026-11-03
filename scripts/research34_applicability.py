"""Independent applicability certificates, model-label gate, then native SVA gate.

Only archived development inputs are used. No evaluated SVA defines applicability.
No property is supplied to or rewritten for a model.
"""
import copy
import hashlib
import json
from pathlib import Path
import research17_loop as loop
from research15_evidence import marker_map
from research28_report import portable
from research33_model import Model as SvaModel
from research20_remote import RemoteModel
from research32_model import assemble
import research31_gate as history_gate

read,dump=loop.read,loop.dump
LABELS=('required','cancelled','not_required','unknown')


def certificate(record, cycle):
    """Use the independent port-history oracle and actual reset samples."""
    rows={r['cycle']:r for r in record['trace']}
    sampled={r['cycle']:r for r in record['reference_trace']}
    previous,now=rows.get(cycle-1),rows.get(cycle)
    result=dict(anchor_cycle=cycle-1,check_cycle=cycle,applicability='unknown')
    n=record['native'];o=record['oracle']
    if not (previous and now and record['sampling_qualification']['status']=='passed' and
            n['compile_status']=='passed' and n['execution_status']=='completed' and
            n['tool_support_status']=='supported_for_compiled_constructs' and o['legality']=='legal' and not o['unknown']):
        return result
    if any(rows[c].get(k)!=sampled.get(c,{}).get(k) or rows[c].get(k) is None
           for c in (cycle-1,cycle) for k in ('rst','mvalid','mready','mdata')):return result
    checks=[c for c in o['checks'] if c['cycle']==cycle and c['obligation']=='stall_stability']
    independent=[c for c in loop.fifo.oracle(record['trace'])['checks'] if c['cycle']==cycle and c['obligation']=='stall_stability']
    if checks!=independent:return result
    pending=not previous['rst'] and previous['mvalid'] and not previous['mready']
    if pending and now['rst']:
        label='cancelled' if not checks else 'unknown'
    elif pending and not now['rst']:
        label='required' if len(checks)==1 else 'unknown'
    else:label='not_required' if not checks else 'unknown'
    return dict(**{k:v for k,v in result.items() if k!='applicability'},applicability=label,
                oracle_checks=checks,samples=[sampled[cycle-1],sampled[cycle]],
                reason='Independent port-history check plus reset cancellation; no candidate predicate inspected.')


def build_windows(baseline):
    info=loop.inspect(baseline['group']['ledger']);public=[];expected=[]
    def add(record,cycle,source,category,paired=None):
        cert=certificate(record,cycle);ident=f'w{len(public)}'
        assert cert['applicability']!='unknown',f'unqualified_window:{category}'
        item=dict(id=ident,anchor_sample=cert['samples'][0],check_sample=cert['samples'][1])
        if paired:
            other=certificate(paired,cycle)
            assert other['applicability']==cert['applicability']
            item['paired_samples']=other['samples']
        public.append(item)
        expected.append(dict(id=ident,**cert,category=category,source=str(source),
                             source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    for key in sorted(info['misses']):
        row=info['rows'][key]
        if row['obligation']!='stall_stability':continue
        path=portable(row['source_directory'])/'replay.json';faulty=read(path)
        fixed=read(path.parent.parent/'correct/replay.json')
        assert row['oracle']['legality']=='legal' and row['oracle']['paired_control_pass'] and row['oracle']['identical_input_handshakes']
        add(faulty,row['cycle'],path,'target:'+row['variant'],fixed)
    source=portable(baseline['group']['ledger'][0]['source_directory'])/'replay.json'
    # Always take a correct-side history record, never an assertion-selected truth label.
    source=source.parent.parent/'correct/replay.json';record=read(source)
    picked=set()
    for previous,now in zip(record['trace'],record['trace'][1:]):
        c=certificate(record,now['cycle']);label=c['applicability']
        category=None
        if label=='cancelled':category='reset_cancels_pending_stall'
        elif label=='not_required':
            if previous['rst'] and not now['rst']:category='first_sample_after_reset'
            elif not previous['rst'] and not now['rst'] and not previous['mvalid']:category='idle_no_output'
            elif not previous['rst'] and not now['rst'] and previous['mvalid'] and previous['mready']:category='accepted_output_no_stall'
        elif label=='required' and now['mready']:category='legal_release_requires_hold'
        if category and category not in picked:
            picked.add(category);add(record,now['cycle'],source,category)
    assert len(public)==9 and len(picked)==5,(len(public),picked)
    return public,expected


def validate_plan(value, expected):
    reasons=[];actual={}
    if not isinstance(value,dict) or set(value)!={'windows'} or not isinstance(value.get('windows'),list):
        return dict(accepted=False,reasons=[dict(kind='plan_schema')],stage='applicability')
    for row in value['windows']:
        if not isinstance(row,dict) or set(row)!={'id','anchor_cycle','check_cycle','applicability'} or not isinstance(row.get('id'),str) or row.get('id') in actual:
            reasons.append(dict(kind='malformed_or_duplicate_window'));continue
        actual[row['id']]=row
    if set(actual)!={r['id'] for r in expected}:reasons.append(dict(kind='missing_or_extra_windows'))
    for truth in expected:
        row=actual.get(truth['id'])
        if row is None:continue
        for field in ('anchor_cycle','check_cycle','applicability'):
            if row[field]!=truth[field] or (field.endswith('cycle') and type(row[field]) is not int):
                reasons.append(dict(kind='incorrect_'+field,id=truth['id'],expected=truth[field],actual=row[field]))
        if row['applicability']=='unknown' or truth['applicability']=='unknown':
            reasons.append(dict(kind='unknown_is_not_a_pass',id=truth['id']))
    return dict(accepted=not reasons,reasons=reasons,stage='applicability',windows=len(expected),
                scope='These development windows only; no general specification understanding claim.')


def plan_request(preview,windows):
    request=copy.deepcopy(preview);body=json.loads(preview['messages'][1]['content'])
    task=dict(task='Identify when the confirmed stall_stability obligation applies. Do not generate SVA in this stage.',
              specification=body['counterexample_first']['specification'],
              clock_and_reset=body['counterexample_first']['clock_and_reset'],windows=windows,
              response_schema=dict(windows=[dict(id='given window id',anchor_cycle='integer input anchor cycle',
                   check_cycle='integer input check cycle',applicability=list(LABELS))]),
              labels='required: output must retain valid and payload at the check sample; cancelled: a pending stall obligation is cancelled by reset at the check sample; not_required: no stall hold requirement for this transition; unknown: cannot establish applicability. Return exactly one record per window, no explanations or SVA.',
              rtl_and_common_contract=body['rtl_and_common_contract'])
    request['messages']=[dict(role='system',content='Label hardware obligation applicability from sampled RTL observations and the specification. Return only the requested JSON; do not invent a property.'),dict(role='user',content=json.dumps(task))]
    return request


class PlanModel(RemoteModel):
    output_kind='applicability_plan'
    def __init__(self,out,settings,payload):
        super().__init__(out,settings);self.payload=payload
    def _payload(self,*args,**kwargs):return copy.deepcopy(self.payload)
    def save_decoded_output(self,folder,value,current,secret):
        # Preserve even incorrect plans; semantic validation is a separate gate.
        dump(folder/'applicability_plan.json',value)
        return value,'applicability_plan_received_not_validated'


class VerifiedPlanModel(SvaModel):
    def __init__(self,out,settings,plan):
        super().__init__(out,settings);self.plan=plan
    def transform_request(self,*args,**kwargs):
        request=super().transform_request(*args,**kwargs)
        body=json.loads(request['messages'][1]['content'])
        body['verified_model_applicability_plan']=self.plan
        body['execution_contract']='Your applicability labels passed an independent transaction/reset check. Generate a property whose native antecedent actually covers each required target transition and whose native failure detects the violation while the legal paired RTL passes. The test harness will evaluate actual triggers before full history replay. No property will be silently corrected.'
        request['messages'][1]['content']=json.dumps(body)
        return request


def native_target_gate(before,after,edited_id):
    reasons=[];targets=loop.inspect(before['group']['ledger'])['misses'];rows=[]
    if not after.get('group') or not after['healthy']:
        reasons.append(dict(kind='native_or_sampling_or_legal_control_failure'))
    if after.get('group'):
        actual=loop.inspect(after['group']['ledger'])
        for key in sorted(targets):
            row=actual['rows'].get(key)
            if not row:
                reasons.append(dict(kind='missing_target_row',evidence_id=key));continue
            prop=next((a for a in row['native']['assertions'] if a['id']==edited_id),None)
            correct=read(portable(row['source_directory']).parent/'correct/replay.json')
            candidate=next(a for a in correct['candidate']['assertions'] if a['id']==edited_id)
            cycle=row['cycle']-candidate['derived_delay']
            control_trigger=cycle in marker_map(correct['native'],'triggers').get(edited_id,set())
            evidence=dict(evidence_id=key,check_cycle=row['cycle'],native_antecedent_cycle=cycle,
                          edited_assertion=prop,correct_side_trigger=control_trigger)
            rows.append(evidence)
            if not prop or not prop['trigger'] or not control_trigger:
                reasons.append(dict(kind='required_transition_not_triggered',**evidence))
            if not prop or not prop['causal_detection']:
                reasons.append(dict(kind='target_not_causally_detected',evidence_id=key))
        historical=history_gate.decide(before['group']['ledger'],after['group']['ledger'],sorted(targets))
        if not historical['accepted']:reasons+=historical['reasons']
    return dict(accepted=not reasons,reasons=reasons,target_rows=rows,stage='native_target_trigger_and_detection',
                full_history_authorized=not reasons,scope='Small paired development replay; passing still requires complete history replay.')
