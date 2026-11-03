"""Model-owned AST continuation; reuse native/history/freeze/holdout gates.

No expression or successful assertion is supplied by this adapter. Recursive
AST syntax is constrained locally; remote JSON schema is NOT provider-enforced.
"""
import argparse
import copy
import json
from pathlib import Path

import research17_loop as loop
import research17_model_schema as grammar
import research38_history_feedback as previous
from research32_model import assemble as assemble_text
from research34_campaign import digest

read, dump = loop.read, loop.dump


def schema(current):
    result = grammar.schema()
    result['required'] = ['operation', 'assertion_id', 'assertions', 'reason']
    result['properties']['operation']['enum'] = ['replace_one']
    result['properties']['assertion_id'] = dict(type='string', enum=[
        a['id'] for a in current['assertions'] if 'stall_stability' in a['obligations']])
    items = result['properties']['assertions']
    items['minItems'] = items['maxItems'] = 1
    items['items']['properties']['obligation'] = dict(type='array', minItems=1,
        maxItems=1, items=dict(type='string', enum=['stall_stability']))
    return result


def render_edit(value, current):
    """Syntax-only, strict AST rendering. Never parse or fix text expressions."""
    require = grammar._require
    require(type(value) is dict and set(value) == {'operation','assertion_id','assertions','reason'},
            'edit_fields', '$', 'Require operation, assertion_id, assertions and reason.')
    require(value['operation'] == 'replace_one', 'operation', '$.operation', 'One target replacement required.')
    require(value['assertion_id'] in schema(current)['properties']['assertion_id']['enum'],
            'target_slot', '$.assertion_id', 'Choose an existing stall_stability slot.')
    require(type(value['reason']) is str and len(value['reason']) <= 128,
            'reason', '$.reason', 'At most 128 characters.')
    require(type(value['assertions']) is list and len(value['assertions']) == 1,
            'assertion_count', '$.assertions', 'Exactly one assertion.')
    item = value['assertions'][0]
    require(type(item) is dict and set(item) == {'antecedent','consequent','timing','obligation'},
            'assertion_fields', '$.assertions[0]', 'Require both AST operands, timing and obligation.')
    require(item['obligation'] == ['stall_stability'], 'obligation', '$.assertions[0].obligation',
            'Preserve the chosen target obligation.')
    require(item['timing'] in ('same_sample','next_sample'), 'timing', '$.assertions[0].timing',
            'Choose same_sample or next_sample.')
    rendered = copy.deepcopy(value)
    for side in ('antecedent','consequent'):
        # Current qualified_sampled_multi_v2 supports sampled antecedents too.
        # Keep all choices; the legacy AST normalizer's older frontend limit
        # must not silently restrict current semantics.
        rendered['assertions'][0][side] = grammar.expression(item[side], '$.assertions[0].'+side)
    return rendered


def assemble(value, current):
    return assemble_text(render_edit(value, current), current)


def payload(initial, diagnostic, plan, settings):
    request = previous.payload(initial, diagnostic, plan, settings)
    body = json.loads(request['messages'][1]['content'])
    body['output_schema'] = schema(initial)
    body['expression_interface'] = dict(
        kind='model_owned_recursive_AST', allowed_signals=list(grammar.SIGNALS),
        unary_operators=list(grammar.UNARY), binary_operators=list(grammar.BINARY),
        limits=dict(max_depth=grammar.MAX_DEPTH, max_nodes=grammar.MAX_NODES),
        instructions='Choose every signal, integer, operator, operand, and timing. Use objects with signal, int, or op/args fields. No raw expression strings. Temporal implication belongs only in timing. The renderer only adds parentheses; native execution and historical gates decide correctness.',
        reset='The harness supplies clock and disable iff(rst). Reset appears in observed samples, but clk/rst are not property operand signals.',
        enforcement='Strict local validation. Remote response_format=json_object does not enforce this recursive schema.')
    request['messages'][0]['content'] = ('Generate one native SVA edit as the supplied JSON AST schema. '
        'Select predicates and timing from RTL, obligations and actual development observations. '
        'All expression choices are yours. Syntax rendering does not infer or repair semantics.')
    request['messages'][1]['content'] = json.dumps(body)
    return request


def feedback(result, verdict, call, prior):
    diagnostic = previous.complete_feedback(result, verdict, call)
    if result is None or not result.get('group'):
        # An interface failure has no native samples. Preserve numeric history
        # rather than replacing it with empty lists for the next real request.
        diagnostic['prior_native_development_diagnostics'] = copy.deepcopy(
            prior.get('prior_native_development_diagnostics', prior))
    return diagnostic


class Model(previous.Model):
    def __init__(self, out, settings, plan):
        super().__init__(out, settings, plan)
        self.assemble = assemble
        dump(self.out/'model_schema.json', schema(read(previous.PREP/'shared_initial.json')))

    def _payload(self, current, target, diagnostic, phase):
        return payload(current, diagnostic, self.plan, self.config)

    def save_decoded_output(self, folder, value, current, secret):
        rendered = render_edit(value, current)
        dump(folder/'rendered_edit.json', rendered)
        return super().save_decoded_output(folder, value, current, secret)


def prepare(out):
    previous.prepare(out)
    initial = read(out/'shared_initial.json')
    settings = read(out/'model_config.json')
    settings['expression_format'] = 'recursive_ast_replace_one_v1'
    settings['direct_property'] = False
    dump(out/'model_config.json', settings)
    dump(out/'model_schema.json', schema(initial))
    dump(out/'request.preview.json', payload(initial, read(out/'development_diagnostics.json'),
                                           read(out/'verified_plan.json'), settings))
    protocol = read(out/'protocol.json')
    protocol.update(expression_format='recursive_ast_replace_one_v1', feedback_version=3,
        interface='All Boolean ASTs and timing chosen by model. No text-to-AST conversion, predicate template or semantic correction.',
        qualification='Syntactic/local/native fixtures are diagnostics only, never model repair candidates or model feedback.',
        budget='All previous grants exhausted. New explicit maximum two-call authorization required.')
    dump(out/'protocol.json', protocol)
    dump(out/'prepared_hashes.json', {p.relative_to(out).as_posix():digest(p)
         for p in out.glob('*.json') if p.name != 'prepared_hashes.json'})
    print('PREPARED_AST_CONTINUATION model_calls=0', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare','run'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--prepared', type=Path)
    p.add_argument('--authorization', type=Path)
    a = p.parse_args()
    out = a.out.resolve()
    assert loop.ROOT in out.parents
    if a.action == 'prepare': prepare(out)
    else: previous.run(a.prepared.resolve(), out, a.authorization.resolve(), Model, feedback)
