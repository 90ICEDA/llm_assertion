"""Fresh obligation synthesis without copying prior rejected predicate text.

Only presentation changes. The model still writes every predicate and timing;
research26.replace_one and the existing native historical gate are unchanged.
"""
import copy
import hashlib
import json

from research26_model import Model as PreviousModel
from research26_model import RemoteModel as PreviousRemoteModel
from research21_model import full_trace


class Model(PreviousModel):
    def transform_request(self, request, current, target, feedback, phase):
        request = super().transform_request(request, current, target, feedback, phase)
        return self.present(request, current, target, feedback, phase)

    def present(self, request, current, target, feedback, phase):
        if self.config.get('fresh_unconstrained_property'):
            request['format']['properties']['assertions']['items']['properties']['property'].pop('pattern', None)
        body = json.loads(request['messages'][1]['content'])
        task = body['boundary_repair']
        targets = task['requested_obligations']
        eligible = [a for a in current['assertions']
                    if set(targets) <= set(a['obligations'])]
        assert len(eligible) == 1, 'fresh_synthesis_requires_one_matching_slot'
        slot = eligible[0]['id']
        request['format']['properties']['assertion_id']['enum'] = [slot]
        # Select actual development observations by semantic boundary, not by
        # desired output predicate. Include uncertain attribution explicitly.
        cards = {}
        for entry in feedback.get('actual_native_evidence', []):
            diagnostic = entry['diagnostic']
            for event in diagnostic.get('target_evidence', []):
                if event['obligation'] not in targets or event['gap_observation'] == 'detected':
                    continue
                trace, provenance = full_trace(diagnostic['mutant'])
                sample = trace.get(event['cycle'], {})
                key = sample.get('ref_count', 0) > 0
                if key in cards:
                    continue
                fixed, fixed_provenance = full_trace(diagnostic['fixed'])
                cards[key] = dict(scenario=entry['scenario'], event=copy.deepcopy(event),
                    faulty_samples=[trace.get(c) for c in range(event['cycle']-1, event['cycle']+1)],
                    correct_samples=[fixed.get(c) for c in range(event['cycle']-1, event['cycle']+1)],
                    source=provenance, control_source=fixed_provenance)
        fresh = dict(requested_obligations=targets, specifications=task['specifications'],
            operation=task['operation'], assertion_id=slot,
            old_set_sha256=hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest(),
            old_expression_omitted='Deliberate fresh synthesis to avoid copying repeatedly rejected predicates. Full prior set is archived and replayed unchanged except this slot.',
            requirement='Every accepted output must correspond to the current oldest accepted, uncancelled input. Reset cancels pending inputs. No output is permitted when no such input exists. A cancelled payload must not reappear in place of a different new pending transaction either. Zero is an ordinary payload.',
            observations=list(cards.values()), validation=task['validation'],
            rejection_kinds=task['decision_reasons'],
            interface_diagnostic=task.get('diagnostics'),
            sampling='All supplied samples and reference state are pre-NBA on the assertion clock edge. The independent reference queue has already processed preceding reset edges. ref_expected is meaningful only for a nonempty queue.',
            response_schema=request['format'])
        request['messages'] = [
            dict(role='system', content='Synthesize ONE native SVA from the current transaction obligation and actual observations. Return JSON only. Derive the trigger, required result, and implication timing afresh. The assertion must check every output acceptance, including the faulty ones, rather than assume the required result in its trigger. Do not reconstruct history already represented by the independent reference queue. All other assertions are retained automatically. No property answer is supplied.'),
            dict(role='user', content=json.dumps(dict(
                rtl_and_common_contract=body['rtl_and_common_contract'],
                fresh_obligation_synthesis=fresh,
                final_instruction='Explain which current sampled state establishes transaction existence and identity, then generate the native implication. Do not equate a pre-reset input with a current uncancelled input. Only declared signals; clock and reset wrapper are supplied.'+
                (' This buffered FIFO can legally output while the input port is idle; an input-side handshake is not a precondition for checking an output. The current input payload is unrelated to the head of the outstanding queue. Check existence and identity on the output acceptance edge itself. Native temporal implication belongs between the antecedent and consequent; both sides must be Boolean expressions.' if self.config.get('fresh_unconstrained_property') else ''))))
        ]
        return request


class RemoteModel(PreviousRemoteModel):
    def transform_request(self, request, current, target, feedback, phase):
        request = super().transform_request(request, current, target, feedback, phase)
        request['format'] = json.loads(request['messages'][1]['content'])['boundary_repair']['response_schema']
        # The remote endpoint enforces json_object only. This schema is prompt
        # text, never represented as remote grammar enforcement.
        return Model.present(self, request, current, target, feedback, phase)
