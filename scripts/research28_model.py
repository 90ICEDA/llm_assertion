"""Model-owned valid retention edits from exact paired development evidence."""
import copy
import json
from research26_model import RemoteModel as PreviousRemote, replace_one
from research21_model import full_trace


class RemoteModel(PreviousRemote):
    def __init__(self, out, config):
        super().__init__(out, config)
        self.assemble = self.replace_stall_slot

    @staticmethod
    def replace_stall_slot(value, current):
        eligible = {a['id'] for a in current['assertions'] if a['obligations'] == ['stall_stability']}
        assert value.get('assertion_id') in eligible, 'valid_repair_requires_existing_stall_slot'
        assert value['assertions'][0]['obligation'] == ['stall_stability'], 'valid_repair_obligation_changed'
        return replace_one(value, current)

    def transform_request(self, request, current, target, feedback, phase):
        request = super().transform_request(request, current, target, feedback, phase)
        body = json.loads(request['messages'][1]['content'])
        task = body['boundary_repair']
        assert task['requested_obligations'] == ['stall_stability'] or task['requested_obligations'] == ('stall_stability',)
        cards = {}
        for entry in feedback.get('actual_native_evidence', []):
            d = entry['diagnostic']
            for event in d.get('target_evidence', []):
                if event['obligation'] != 'stall_stability' or event['gap_observation'] == 'detected':
                    continue
                trace, provenance = full_trace(d['mutant'])
                cycle = event['cycle']
                prev, now = trace.get(cycle-1), trace.get(cycle)
                if not prev or not now or not prev['mvalid'] or prev['mready'] or now['mvalid']:
                    continue
                key = bool(now['mready'])
                if key in cards:
                    continue
                fixed, fp = full_trace(d['fixed'])
                cards[key] = dict(scenario=entry['scenario'], event=copy.deepcopy(event),
                    faulty_samples=[prev, now], correct_samples=[fixed.get(cycle-1), fixed.get(cycle)],
                    source=provenance, control_source=fp)
        assert cards, 'no_actual_valid_withdrawal_development_evidence'
        ids = [a['id'] for a in current['assertions'] if 'stall_stability' in a['obligations']]
        task['response_schema']['properties']['assertion_id']['enum'] = ids
        body['output_schema'] = task['response_schema']
        # Replace the inherited reset-specific tail with this obligation's
        # actual observations and semantics, without supplying a predicate.
        body.pop('final_temporal_review', None)
        task['actual_observations'] = list(cards.values())
        task['projection'] = dict(rule='First actual missed valid withdrawal for each ready value; exact adjacent development samples.',
                                  shown=len(cards))
        body['final_temporal_review'] = dict(
            observations=list(cards.values()),
            instructions='An offered valid output that was not accepted must remain valid and retain its data on the next clock edge, both during continued backpressure and when ready rises. Reset interrupts this obligation. Preserve the existing data protection and effective triggers. Choose one eligible existing assertion to replace with your complete property; all other properties including reset protection are retained. Explain the concrete missed observations. Do not guard the check with the required future valid result.')
        request['messages'][1]['content'] = json.dumps(body)
        return request
