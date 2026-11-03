"""Local interface and reject/continue controls using archived real proposals.

Zero new model requests. Archived responses are explicitly control inputs, not
reported as new generations, and never substituted by the real campaign.
"""
import argparse
import copy
from pathlib import Path
import research17_loop as loop
import research31_gate as gate
import research32_runtime as extension
from research32_model import assemble,Model
from research21_loop import refine
import research30_ablation as trial

read,dump=loop.read,loop.dump


def main(prep,out):
    out.mkdir(parents=True,exist_ok=False)
    initial=read(prep/'shared_initial.json')
    archived=loop.ROOT/'deliverables/research31_multiseed_20261020_r01/s3121/arms/B/model_call'
    bad=read(archived/'candidate.json')
    valid=read(loop.ROOT/'deliverables/research28_valid_closed_loop_20261020_r01/core/frozen_candidate.json')
    a=valid['assertions'][4]
    value=dict(operation='replace_one',assertion_id='a4',assertions=[dict(
        antecedent=a['derived_antecedent'],consequent=a['consequent'],
        timing='next_sample',obligation=a['obligations'])],reason=a['reason'])
    assembled=assemble(value,initial)
    # Pure syntax roundtrip: strip parentheses for comparison only, never edit
    # the live generated expression or claim this as a generated candidate.
    assert assembled['assertions'][4]['derived_delay']==a['derived_delay']
    for field in ('derived_antecedent','consequent'):
        assert loop.model.native.unparen(assembled['assertions'][4][field])==loop.model.native.unparen(a[field])
    rejects=[]
    for name,change in (
        ('nested_implication',lambda v:v['assertions'][0].update(consequent='mvalid |=> mvalid')),
        ('unknown_signal',lambda v:v['assertions'][0].update(antecedent='unknown_port')),
        ('over_budget_add',lambda v:v.update(operation='add',assertion_id='')),
        ('changed_mapping',lambda v:v['assertions'][0].update(obligation=['drain_no_loss'])),
    ):
        v=copy.deepcopy(value);change(v)
        try:assemble(v,initial)
        except AssertionError as exc:rejects.append(dict(name=name,diagnostic=str(exc)))
        else:raise AssertionError(('invalid_interface_accepted',name))
    selected=read(prep/'s3203/cases.json')[-4:]
    seen=[]
    class ArchivedControl:
        def call(self,folder,current,target,feedback,phase):
            seen.append(loop.sha(current))
            dump(folder/'control_input.json',dict(source='archived_real_response_replay_control',new_model_calls=0,
                feedback=feedback,not_a_fresh_generation=True))
            candidate=(bad,assembled)[len(seen)-1]
            dump(folder/'model_edit.json',dict(archived_control=True,candidate=candidate))
            return dict(status='archived_control',model_calls=0),candidate
    previous=loop.decide
    try:
        loop.decide=gate.decide
        with extension.installed():
            final,summary=refine(out,ArchivedControl(),initial,selected,2,stages_to_run=(('stall_stability',),))
    finally:loop.decide=previous
    assert len(seen)==2 and seen==[loop.sha(initial)]*2
    assert not summary['history'][0]['decision']['accepted'] and summary['history'][1]['decision']['accepted']
    assert summary['resolved']
    # Real remote presentation must retain actionable interface diagnostics.
    binding=read(prep/'s3203/baseline_binding.json')
    from research31_gate import portable
    before=read(portable(binding['result_path']))
    from research32_campaign import initial_feedback
    feedback=initial_feedback(before)
    feedback.update(previous_rejected_proposal={'actual_archived_diagnostic':True},
        transport_or_interface_diagnostic=dict(candidate_status='interface_rejected',candidate_error=dict(detail='require_exactly_one_explicit_implication')),
        actual_rejection=dict(reasons=[dict(kind='model_or_interface_failure')]))
    with extension.installed():
        llm=Model(out/'diagnostic_preview',trial.config(1))
        payload=llm._payload(initial,'stall_stability',feedback,'qualification_no_request')
    task=__import__('json').loads(payload['messages'][1]['content'])['boundary_repair']
    assert task['diagnostics']['candidate_error']['detail']=='require_exactly_one_explicit_implication'
    assert task['previous_rejected_proposal']==feedback['previous_rejected_proposal']
    dump(out/'outcome.json',dict(status='local_controls_passed',interface_rejections=rejects,
        rejection_diagnostics_preserved=True,rollback_confirmed=True,continued_after_rejection=True,
        new_model_calls=0,scope='Archived controls and actual native execution only; does not establish new model stability.',
        before=summary['before'],after=summary['after']))
    print('LOCAL_CONTROLS_PASSED',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    main(a.prepared.resolve(),out)
