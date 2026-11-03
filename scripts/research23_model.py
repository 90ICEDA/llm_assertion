"""Local schema-constrained boundary edits; predicates remain model-generated."""
import json
from research22_model import LocalModel as PreviousModel
import research17_model as base


def edit_schema():
    return dict(type='object', additionalProperties=False,
        required=['reason', 'operation', 'assertions'], properties=dict(
            reason=dict(type='string'),
            operation=dict(type='string', enum=['add']),
            assertions=dict(type='array', minItems=1, maxItems=1,
                items=dict(type='object', additionalProperties=False,
                    required=['property', 'obligation'], properties=dict(
                        property=dict(type='string', minLength=1, maxLength=1024),
                        obligation=dict(type='array', minItems=1, maxItems=2,
                            items=dict(type='string', enum=list(base.SPECS))))))))


class Model(PreviousModel):
    def __init__(self, out, config):
        super().__init__(out, config)
        self.schema = edit_schema()
        base.dump(self.out/'model_schema.json', self.schema)

    def transform_request(self, request, current, target, feedback, phase):
        request = super().transform_request(request, current, target, feedback, phase)
        body = json.loads(request['messages'][1]['content'])
        task = body['boundary_repair']
        request['format'] = edit_schema()
        request['messages'][0]['content'] = (
            'Repair the requested FIFO boundary obligation, not the existing data-order property. '
            'Return exactly the supplied JSON schema. First explain in reason why the old property '
            'misses the supplied violating samples; then generate ONE new complementary SVA. '
            'The existing properties are retained automatically. Do not duplicate them. '
            'Choose the antecedent, consequent, and implication yourself. '
            'The new property must fail on the actual violating sample, not assume away that sample. '
            'Requested obligations: '+', '.join(task['requested_obligations'])+'. '
            +task['boundary_semantics'])
        # Preserve all RTL and observed data. Place the task first and repeat
        # only the natural-language requirement at the end, never a predicate.
        body = dict(boundary_repair=task,
            rtl_and_common_contract=body['rtl_and_common_contract'],
            final_instruction='Generate a new complementary property for these obligations only: '
                +', '.join(task['requested_obligations'])+'. '+task['boundary_semantics'])
        request['messages'][1]['content'] = json.dumps(body)
        return request
