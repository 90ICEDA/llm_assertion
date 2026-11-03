"""Separate model-owned Boolean operands and timing; no predicate correction.

Reuses the real transport/context and existing native frontend. Remote JSON
schema is a prompt contract, not claimed to be provider-enforced grammar.
"""
import copy
import json
import research17_model as base
from research30_ablation import Model as Parent


def assemble(value, current):
    assert set(value) == {'operation', 'assertion_id', 'assertions', 'reason'}, 'edit_schema'
    assert isinstance(value['reason'], str), 'reason_string'
    if value['operation'] == 'keep':
        assert value['assertion_id'] == '' and value['assertions'] == [], 'keep_schema'
        return copy.deepcopy(current)
    assert value['operation'] in ('replace_one', 'add'), 'edit_operation'
    assert len(value['assertions']) == 1, 'one_edit_per_iteration'
    item = value['assertions'][0]
    assert set(item) == {'antecedent', 'consequent', 'timing', 'obligation'}, 'operand_schema'
    for key in ('antecedent', 'consequent'):
        assert isinstance(item[key], str) and item[key].strip(), 'empty_operand'
        assert not any(x in item[key] for x in ('|->', '|=>', '##')), 'Boolean_operands_only_temporal_choice_in_timing'
    assert item['timing'] in ('same_sample', 'next_sample'), 'timing_enum'
    arrow = '|->' if item['timing'] == 'same_sample' else '|=>'
    prop = dict(property=f"({item['antecedent']}) {arrow} ({item['consequent']})",
                obligations=item['obligation'], reason=value['reason'])
    props = copy.deepcopy(current['assertions'])
    if value['operation'] == 'add':
        assert value['assertion_id'] == '' and len(props) < 5, 'no_free_assertion_slot'
        props.append(prop)
    else:
        ids = [a['id'] for a in props]
        assert value['assertion_id'] in ids, 'unknown_assertion_id'
        old = props[ids.index(value['assertion_id'])]
        assert set(item['obligation']) == set(old['obligations']), 'preserve_declared_obligation_mapping'
        props[ids.index(value['assertion_id'])] = prop
    return base.native.normalize_candidate(dict(assertions=props, syntax_profile='qualified_sampled_multi_v2'))


class Model(Parent):
    def __init__(self, out, settings):
        super().__init__(out, settings)
        self.assemble = assemble

    def transform_request(self, request, current, target, feedback, phase):
        request = super().transform_request(request, current, target, feedback, phase)
        body = json.loads(request['messages'][1]['content'])
        task = body['boundary_repair']
        schema = dict(type='object', additionalProperties=False,
            required=['operation', 'assertion_id', 'assertions', 'reason'], properties=dict(
                operation=dict(type='string', enum=['keep', 'replace_one', 'add']),
                assertion_id=dict(type='string', enum=['']+[a['id'] for a in current['assertions']]),
                reason=dict(type='string'), assertions=dict(type='array', maxItems=1,
                    items=dict(type='object', additionalProperties=False,
                        required=['antecedent', 'consequent', 'timing', 'obligation'], properties=dict(
                            antecedent=dict(type='string'), consequent=dict(type='string'),
                            timing=dict(type='string', enum=['same_sample', 'next_sample']),
                            obligation=dict(type='array', items=dict(type='string', enum=list(base.SPECS))))))))
        task['operation'] = ('Return one edit with separate Boolean antecedent and consequent and timing. '
            'Never place implication or sequence operators inside either Boolean string. '
            'replace_one keeps every other assertion unchanged and retains the chosen assertion obligation mapping. '
            'add is available only with fewer than five existing assertions; keep uses empty assertion_id and assertions. '
            'A rejected edit never replaces the accepted set. Use actual rejection diagnostics to produce a new edit.')
        task['response_schema'] = schema
        task['previous_rejected_proposal'] = feedback.get('previous_rejected_proposal')
        task['actual_rejection'] = feedback.get('actual_rejection')
        task['original_missing_evidence'] = feedback.get('original_gap_cards')
        task.pop('rejected_proposal_projection', None)
        body['output_schema'] = schema
        body['final_instruction'] = task['operation'] + ' ' + task['boundary_semantics']
        request['messages'][0]['content'] = ('Generate a native SVA edit from the specification and actual observations. '
            'Return exactly the supplied JSON schema. You choose both Boolean operands and temporal timing. '
            'No predicate is supplied or corrected. The harness supplies clock/reset. Preserve prior protection.')
        request['messages'][1]['content'] = json.dumps(body)
        return request
