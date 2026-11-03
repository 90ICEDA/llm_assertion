"""Compact real-model requests; exact RTL, observed samples, no supplied SVA answer."""
import copy
import json
import research17_model as base
from research21_model import paired_feedback
from research20_remote import RemoteModel
from research20_model import Model as ContextModel


class Model(RemoteModel):
    def transform_request(self, request, current, target, feedback, phase):
        request=ContextModel.transform_request(self,request,current,target,feedback,phase)
        original=json.loads(request['messages'][1]['content'])
        context=original['rtl_and_common_contract']
        observed=paired_feedback(feedback,target)
        cards=[]
        for pair in observed['paired_target_samples'][:2]:
            card={k:copy.deepcopy(pair[k]) for k in ('scenario','cycle','target_evidence')}
            for side in ('fixed','mutant'):
                card[side]={k:copy.deepcopy(pair[side][k]) for k in
                    ('mode','adjacent_samples','independent_oracle','full_trace_provenance') if k in pair[side]}
            cards.append(card)
        targets=feedback.get('requested_obligations',[target])
        common={k:context[k] for k in ('rtl_shared','rtl_before','rtl_after',
            'actual_testbench_and_fault_boundaries','reference_rtl','signals','clock_reset',
            'temporal_semantics','provenance') if k in context}
        common['allowed_property_signals']=list(base.SIGNALS)
        common['syntax']='Only an implication expression in property. The harness adds clock, reset disable, assert and cover. No clk/rst identifiers, declarations, labels, or semicolons in property.'
        task=dict(phase=phase,requested_obligations=targets,
            specifications={o:base.SPECS[o] for o in targets},
            accepted_properties=[dict(property=a['property'],obligation=a['obligations']) for a in current['assertions']],
            actual_observations=cards,legal_failure_observations=observed['legal_control_failure_samples'][:1],
            diagnostics=observed['interface_diagnostic'],
            previous_rejected_proposal=feedback.get('previous_rejected_proposal'),
            decision_reasons=sorted({r['kind'] for r in feedback.get('actual_rejection',{}).get('reasons',[])}),
            operation='Add one complementary property; existing accepted properties are automatically retained. Maximum five properties total.',
            validation='All development records replayed after every edit. Must detect current missing violations without new legal false alarms or lost historical detections/triggers.',
            response_schema=dict(operation='add',assertions=[dict(property='your complete implication expression',
                obligation=targets)],reason='Briefly explain sampling and why the actual violating sample fails.'),
            projection=dict(available_pairs=observed['selection']['available'],shown=len(cards),
                rule='First two actual misses ranked by boundary; exact adjacent samples. No generated example or altered value. Full historical replay is unchanged.'))
        if target=='stall_stability':
            task['boundary_semantics']='When an output is valid but not accepted at sample t, it must still be valid with the same payload at t+1, regardless of ready at t+1. Reset disables interrupted checks. Do not assume stability in the antecedent: it is the required outcome. |-> checks the same edge; |=> checks the following edge.'
        else:
            task['boundary_semantics']='Every accepted output needs a previously accepted, uncancelled input in the sampled queue. Reset cancels pending inputs. Any output without such an input is forbidden, INCLUDING zero data. Payload value is irrelevant to whether a transaction exists. The wrapper already handles reset; do not mention rst in the expression.'
        request['messages']=[dict(role='system',content='You are writing a native SystemVerilog assertion edit. Derive the predicate from the specification and actual counterexample. Return only JSON. Do not copy a required outcome into the antecedent, or guard away the faulty event. You choose all expressions; no semantic correction follows.'),
            dict(role='user',content=json.dumps(dict(rtl_and_common_contract=common))),
            dict(role='user',content=json.dumps(dict(boundary_repair=task)))]
        return request


class LocalModel(base.Model):
    """Same exact context; single user message on the existing local service."""
    def __init__(self,out,config):
        super().__init__(out,config)
        from research20_model import assemble
        self.assemble=assemble

    def transform_request(self,request,current,target,feedback,phase):
        # Presentation method only; no RemoteModel initialization or request.
        request=Model.transform_request(self,request,current,target,feedback,phase)
        common=json.loads(request['messages'][1]['content'])
        task=json.loads(request['messages'][2]['content'])
        request['messages']=[request['messages'][0],dict(role='user',content=json.dumps({**common,**task}))]
        request['format']='json'
        return request
