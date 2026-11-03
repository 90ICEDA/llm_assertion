"""Model-owned boundary repairs with paired, adjacent native observations.

No candidate expression is supplied, substituted, or repaired by this adapter.
"""
import copy
import hashlib
import json
from pathlib import Path
import research17_model as base
from research19_feedback import focus_feedback, _sample, _native_at
from research20_model import assemble
from research20_remote import RemoteModel


def full_trace(record):
    """Read only the supplied development replay, never independent results."""
    source=record.get('artifacts', {})
    value=source.get('reference_trace')
    if not value:return {}, dict(status='unavailable')
    raw=str(value).replace('\\','/')
    root_marker='/AssertionForge-main1/'
    relative=raw.split(root_marker,1)[1] if root_marker in raw else None
    path=(base.ROOT/relative).resolve() if relative else Path(value).resolve()
    if base.ROOT not in path.parents or 'core_independent' in path.parts or 'core' not in path.parts:
        raise ValueError('feedback_trace_must_be_current_development_replay')
    if path.name!='reference_trace.json':raise ValueError('unexpected_feedback_trace_name')
    data=path.read_bytes();samples=json.loads(data)
    return {s['cycle']:s for s in samples},dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),status='actual_development_trace')


def paired_feedback(feedback, target):
    full = focus_feedback(feedback, target)
    entries = {e['scenario']: e['diagnostic'] for e in feedback.get('actual_native_evidence', [])}
    pairs = full['paired_target_samples']
    # Show actual misses before already detected examples. Prefer the released
    # boundary / ordinary zero payload without changing any recorded value.
    def rank(pair):
        sample = pair['mutant'].get('sample') or {}
        return (pair['target_evidence'].get('gap_observation') == 'detected',
                not (sample.get('mready') == 1 if target == 'stall_stability' else sample.get('mdata') == 0))
    pairs = sorted(pairs, key=rank)
    selected = []
    for pair in pairs[:4]:
        pair = copy.deepcopy(pair)
        diagnostic = entries.get(pair['scenario'], {})
        for side in ('fixed', 'mutant'):
            source = diagnostic.get(side, {})
            trace,provenance=full_trace(source)
            pair[side]['sample']=copy.deepcopy(trace.get(pair['cycle'],_sample(source,pair['cycle'])))
            pair[side]['adjacent_samples'] = [copy.deepcopy(trace.get(c,_sample(source,c))) for c in range(pair['cycle']-1, pair['cycle']+2)]
            pair[side]['full_trace_provenance']=provenance
            pair[side]['adjacent_native_markers'] = [dict(cycle=c, properties=_native_at(source, c))
                for c in range(pair['cycle']-1, pair['cycle']+2)]
        selected.append(pair)
    result = dict(paired_target_samples=selected,
        legal_control_failure_samples=full['legal_control_failure_samples'][:2],
        counts=feedback.get('counts'),
        selection=dict(available=len(pairs), shown=len(selected), policy='Actual misses first; then release edge or zero payload. Adjacent source samples unchanged; missing samples remain null.'),
        historical_replay='Every proposal must preserve all accepted detections, legal controls and obligation triggers on the entire development set.')
    for key in ('actual_rejection', 'previous_rejected_proposal', 'accepted_version_retained'):
        if key in feedback: result[key] = feedback[key]
    diagnostic = feedback.get('transport_or_interface_diagnostic', {})
    result['interface_diagnostic'] = {k:diagnostic[k] for k in ('status','candidate_status','candidate_error') if k in diagnostic}
    return result


class Model(RemoteModel):
    def transform_request(self, request, current, target, feedback, phase):
        # Keep the existing exact RTL, independent reference, clock/reset and
        # wrapper context. Replace only the lossy single-cycle feedback view.
        request = super().transform_request(request, current, target, feedback, phase)
        payload = json.loads(request['messages'][1]['content'])
        context, task = payload['rtl_and_common_contract'], payload['requested_work']
        task['actual_feedback'] = paired_feedback(feedback, target)
        task['available_total_assertion_slots'] = 5-len((current or {}).get('assertions', []))
        context['property_signal_allowlist'] = ['svalid','sready','sdata','mvalid','mready','mdata','ref_count','ref_expected','drain_due']
        context['wrapper_only_identifiers'] = 'clk and rst are NOT property-expression signals. The harness supplies the clock and disables the property during reset. Do not write either identifier in any property string.'
        if target == 'stall_stability':
            task['boundary_requirement'] = ('A valid output sampled under backpressure must retain valid and payload at the next sample, including when ready becomes high at that next sample. Reset disables interrupted checks. Inspect both adjacent samples: requiring backpressure at the next sample skips the release boundary. Preserve the previous accepted checks.')
        else:
            task['boundary_requirement'] = ('Each accepted output must correspond to an outstanding accepted input in the independent pre-NBA queue. Reset empties that queue and cancels its pending transactions. After reset a resurrected output is forbidden even if its payload is zero. Compare the zero and nonzero violating samples against the legal paired control. Do not infer legality from payload value. Protect both no_unsolicited_output and reset_cancellation when applicable.')
        task['response_requirements'] = ('Return only JSON with exactly operation, assertions, reason. Each new item has exactly property and obligation (singular field, value string or list). A property is a complete implication expression only, with no clock/reset wrapper or semicolon. Add only new complementary properties; retained properties remain unchanged. Choose every predicate yourself and explain its applicability to the supplied actual samples.')
        # Put concrete boundary samples before the long RTL context. These are
        # a projection of archived values, not hand-written assertion answers.
        cards=[]
        for pair in task['actual_feedback']['paired_target_samples']:
            cards.append(dict(scenario=pair['scenario'],violation_cycle=pair['cycle'],
                independent_judgment=pair['target_evidence'],
                faulty_samples=pair['mutant']['adjacent_samples'],correct_samples=pair['fixed']['adjacent_samples'],
                native_markers=pair['mutant']['adjacent_native_markers']))
        review=dict(requested_obligations=task['requested_obligations'],requirement=task['boundary_requirement'],
            observed_examples=cards,rejected_proposal=feedback.get('previous_rejected_proposal'),
            actual_rejection=feedback.get('actual_rejection'),
            reasoning_check='Check antecedent and consequent separately on the violation edge (or antecedent on the previous edge for nonoverlapped implication). A consequent copied into its own antecedent makes the check vacuous. A guard false on the violation cannot repair that gap. Do not repeat a rejected expression. The reason must match the actual temporal semantics: |-> checks the same edge; |=> checks the next edge.',
            payload_semantics='Zero is an ordinary payload, not proof that no transaction occurred.',
            schema=context['response_schema'])
        request['messages'][1]['content'] = json.dumps(payload)
        request['messages'].insert(1,dict(role='user',content=json.dumps(review)))
        # End with the actual counterexample and a short semantic question;
        # the long RTL must not bury the decision the model needs to make.
        missing=next((p for p in task['actual_feedback']['paired_target_samples']
            if p['target_evidence'].get('gap_observation')!='detected'),None)
        if missing:
            observed={side:missing[side]['adjacent_samples'][:2] for side in ('fixed','mutant')}
            if target=='stall_stability':
                question=('At the first sample the output is stalled. At the second sample backpressure is RELEASED. '
                    'The faulty output changes its payload while the correct output preserves it. '
                    'The required check starts at the stalled sample and constrains the following sample regardless of its ready value. '
                    'Do NOT require the second sample to remain stalled: that skips this counterexample. '
                    'Do NOT assume the payload is already stable in the antecedent: stability is what must be checked. '
                    'Choose the appropriate implication timing; overlapped implication does not mean the next sample. ')
            else:
                question=('This faulty output was accepted after reset despite the queue having NO outstanding accepted transaction. '
                    'Its data may be zero or nonzero; both are forbidden. The correct RTL produces no such output. '
                    'Check whether every accepted output has an outstanding transaction, using the supplied sampled queue count. '
                    'Do NOT prescribe a payload value for an unsolicited output. Reset handling is already supplied by the harness. ')
            request['messages'].append(dict(role='user',content=question+'\nActual adjacent pre-NBA samples: '+json.dumps(observed)+
                '\nPreserve the accepted set and add ONE complementary property for '+', '.join(task['requested_obligations'])+
                '. Return only JSON with operation, assertions, reason; each item has property and obligation. '
                'The property string contains only your implication expression. Explain briefly why its antecedent actually triggers this counterexample and its consequent rejects it.'))
        return request
