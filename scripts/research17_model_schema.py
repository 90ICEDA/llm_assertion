"""Model-owned expression AST -> native SVA, without semantic repair.

The grammar deliberately exposes every signal, operator, integer and implication
choice to the model. It contains no obligation-specific predicate templates.
This is a declared SVA subset, not a general SystemVerilog parser. A schema-valid
answer may still fail native compilation or be semantically wrong.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

SIGNALS = ('svalid', 'sready', 'sdata', 'mvalid', 'mready', 'mdata',
           'ref_count', 'ref_expected', 'drain_due')
OBLIGATIONS = ('order_payload', 'no_unsolicited_output', 'stall_stability',
               'drain_no_loss', 'reset_cancellation')
BINARY = ('&&', '||', '==', '!=', '<', '>', '<=', '>=', '+', '-')
UNARY = ('!', '$past', '$stable', '$rose', '$fell', '$changed')
SAMPLED = set(UNARY) - {'!'}
MAX_DEPTH = 8
MAX_NODES = 63


def _object(properties):
    return dict(type='object', additionalProperties=False,
                required=list(properties), properties=properties)


def schema():
    """Raw JSON Schema suitable for Ollama's format field (not a wrapper)."""
    ref = {'$ref': '#/$defs/expression'}
    expression = dict(anyOf=[
        _object({'signal': dict(type='string', enum=list(SIGNALS))}),
        _object({'int': dict(type='integer', minimum=-2147483648, maximum=2147483647)}),
        _object({'op': dict(type='string', enum=list(UNARY)),
                 'args': dict(type='array', minItems=1, maxItems=1, items=ref)}),
        _object({'op': dict(type='string', enum=list(BINARY)),
                 'args': dict(type='array', minItems=2, maxItems=2, items=ref)}),
    ])
    result = _object(dict(
        operation=dict(type='string', enum=['keep', 'add', 'replace']),
        assertions=dict(type='array', maxItems=3, items=_object(dict(
            antecedent=ref, consequent=ref,
            timing=dict(type='string', enum=['same_sample', 'next_sample']),
            obligation=dict(type='string', enum=list(OBLIGATIONS))))),
        # llama.cpp rejects large bounded repetitions in generated grammars.
        # Keep transport explanations short; normalize still enforces 4096 as
        # a defensive local bound for archived/external model responses.
        reason=dict(type='string', maxLength=128)))
    result['$defs'] = {'expression': expression}
    return result


class SchemaError(ValueError):
    def __init__(self, code, path, detail):
        self.code, self.path, self.detail = code, path, detail
        super().__init__(f'{code} at {path}: {detail}')


def _require(condition, code, path, detail):
    if not condition:
        raise SchemaError(code, path, detail)


def expression(node, path='$', antecedent=False):
    """Strictly render a model-selected AST; never infer missing operands."""
    budget = [0]
    def walk(value, location, depth):
        budget[0] += 1
        _require(depth <= MAX_DEPTH and budget[0] <= MAX_NODES,
                 'expression_complexity_limit', location,
                 f'max depth={MAX_DEPTH}, max nodes={MAX_NODES}')
        _require(type(value) is dict, 'expression_object_required', location,
                 'Use a signal leaf, integer leaf, or operator with AST operands; no SVA strings.')
        fields = set(value)
        if fields == {'signal'}:
            _require(type(value['signal']) is str and value['signal'] in SIGNALS,
                     'unknown_signal', location, 'Choose a declared interface signal.')
            return value['signal']
        if fields == {'int'}:
            n = value['int']
            _require(type(n) is int and -2147483648 <= n <= 2147483647,
                     'integer_out_of_range', location, 'Require a signed 32-bit integer, not Boolean.')
            return f'({n})' if n < 0 else str(n)
        _require(fields == {'op', 'args'}, 'expression_fields', location,
                 'Exactly {signal}, {int}, or {op,args} is required.')
        op, args = value['op'], value['args']
        _require(type(op) is str and op in UNARY + BINARY,
                 'unsupported_operator', location, 'Temporal implication belongs only in timing.')
        arity = 1 if op in UNARY else 2
        _require(type(args) is list and len(args) == arity, 'operator_arity', location,
                 f'{op} requires exactly {arity} operands.')
        _require(not (antecedent and op in SAMPLED), 'sampled_antecedent_unsupported', location,
                 'This native cover frontend permits sampled-value functions only in consequents.')
        rendered = [walk(v, f'{location}.args[{i}]', depth + 1) for i, v in enumerate(args)]
        if op == '!':
            return f'(!({rendered[0]}))'
        if op in SAMPLED:
            return f'{op}({rendered[0]})'
        return f'({rendered[0]} {op} {rendered[1]})'
    return walk(node, path, 0)


def normalize(model_json, current=None):
    """Validate the entire edit and return a research15 native candidate.

    add appends only the supplied assertions; replace is the complete new set.
    A keep edit requires an existing candidate and zero added assertions.
    Native acceptance/replay is mandatory after this syntactic transformation.
    """
    import research15_native_interface as native
    _require(type(model_json) is dict and set(model_json) == {'operation', 'assertions', 'reason'},
             'edit_fields', '$', 'Exactly operation, assertions and reason are required.')
    operation, items, reason = (model_json[k] for k in ('operation', 'assertions', 'reason'))
    _require(type(operation) is str and operation in ('keep', 'add', 'replace'),
             'operation', '$.operation', 'Choose keep, add or replace.')
    _require(type(reason) is str and len(reason) <= 4096, 'reason', '$.reason',
             'Reason must be a string of at most 4096 characters.')
    _require(type(items) is list and len(items) <= 3, 'assertion_count', '$.assertions',
             'At most three edited assertions are allowed per request.')
    if operation == 'keep':
        _require(current is not None and not items, 'invalid_keep', '$',
                 'keep requires an existing candidate and an empty assertion array.')
        return native.normalize_candidate(copy.deepcopy(current))
    _require(bool(items), 'empty_edit', '$.assertions', 'add and replace require assertions.')
    properties = []
    for i, item in enumerate(items):
        path = f'$.assertions[{i}]'
        _require(type(item) is dict and set(item) == {'antecedent', 'consequent', 'timing', 'obligation'},
                 'assertion_fields', path, 'Require antecedent AST, consequent AST, timing and obligation.')
        timing, obligation = item['timing'], item['obligation']
        _require(type(timing) is str and timing in ('same_sample', 'next_sample'),
                 'timing', path+'.timing', 'Choose same_sample or next_sample.')
        _require(type(obligation) is str and obligation in OBLIGATIONS,
                 'unknown_obligation', path+'.obligation', 'Choose one declared obligation.')
        ant = expression(item['antecedent'], path+'.antecedent', antecedent=True)
        cons = expression(item['consequent'], path+'.consequent')
        implication = '|->' if timing == 'same_sample' else '|=>'
        properties.append(dict(property=f'({ant}) {implication} ({cons})',
                               obligations=[obligation], reason=reason))
    if operation == 'add':
        properties = copy.deepcopy((current or {}).get('assertions', [])) + properties
    try:
        return native.normalize_candidate(dict(assertions=properties))
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        raise SchemaError('native_frontend_rejected', '$', str(exc)) from exc


def error_feedback(error):
    """A diagnostic payload for a subsequent real model request; no repair."""
    return dict(status='interface_rejected',
                code=getattr(error, 'code', 'invalid_model_output'),
                path=getattr(error, 'path', '$'),
                detail=getattr(error, 'detail', str(error)),
                semantics_rewritten=False,
                action='Return a new schema-conforming edit; choose all predicates and timing yourself.')


def selftest(out):
    """Syntactic unit fixtures only; never used as experiment candidates."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    tests = []
    def check(name, action, expected_error=None):
        try:
            result = action()
            assert expected_error is None, f'Expected {expected_error}'
            tests.append(dict(name=name, passed=True))
            return result
        except SchemaError as exc:
            assert exc.code == expected_error, (name, exc.code, expected_error)
            tests.append(dict(name=name, passed=True, diagnostic=error_feedback(exc)))
    sig = lambda name: {'signal': name}
    literal = lambda n: {'int': n}
    op = lambda name, *args: {'op': name, 'args': list(args)}
    for name in BINARY:
        check('binary_'+name, lambda name=name: expression(op(name, sig('sdata'), literal(2))))
    for name in UNARY:
        check('unary_'+name, lambda name=name: expression(op(name, sig('mvalid'))))
    check('nested_boolean', lambda: expression(op('&&', op('!', sig('svalid')),
          op('||', sig('mvalid'), op('>', sig('sdata'), op('-', literal(3), literal(1)))))))
    check('raw_temporal_string', lambda: expression('mvalid |-> mready'), 'expression_object_required')
    check('injected_signal', lambda: expression(sig('mvalid |-> mready')), 'unknown_signal')
    check('injected_operator', lambda: expression(op('|=>', sig('mvalid'), sig('mready'))), 'unsupported_operator')
    check('arity', lambda: expression(op('==', literal(1))), 'operator_arity')
    check('bool_is_not_integer', lambda: expression(literal(True)), 'integer_out_of_range')
    check('antecedent_sampled', lambda: expression(op('$past', sig('svalid')), antecedent=True),
          'sampled_antecedent_unsupported')
    check('extra_field', lambda: expression({'signal':'svalid', 'int':0}), 'expression_fields')
    deep = sig('svalid')
    for _ in range(MAX_DEPTH + 1): deep = op('!', deep)
    check('depth_limit', lambda: expression(deep), 'expression_complexity_limit')
    # Arbitrary syntax fixtures, not contract-correct FIFO assertion examples.
    edit = dict(operation='replace', reason='syntactic unit fixture only', assertions=[dict(
        antecedent=sig('svalid'), consequent=op('||', sig('mready'), sig('mvalid')),
        timing='next_sample', obligation='stall_stability')])
    candidate = check('native_frontend_disjunction', lambda: normalize(edit))
    check('keep', lambda: normalize(dict(operation='keep', assertions=[], reason='unit'), candidate))
    check('keep_without_current', lambda: normalize(dict(operation='keep', assertions=[], reason='unit')),
          'invalid_keep')
    check('duplicate_property', lambda: normalize({**edit, 'operation':'add'}, candidate),
          'native_frontend_rejected')
    check('empty_replace', lambda: normalize(dict(operation='replace', assertions=[], reason='unit')),
          'empty_edit')
    check('top_extra_field', lambda: normalize({**edit, 'extra': 1}), 'edit_fields')
    schema_validation = 'unavailable'
    try:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(schema())
        jsonschema.validate(edit, schema())
        schema_validation = 'schema_and_unit_fixture_validated'
    except ImportError:
        pass
    result = dict(passed=all(t['passed'] for t in tests), tests=tests,
        count=len(tests), jsonschema_validation=schema_validation,
        model_calls=0, native_compilations=0, scope='syntax only; not RTL or model success',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        docs='https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx',
        backend_recursive_schema_support='not yet empirically probed; main run must verify')
    (out/'schema.json').write_text(json.dumps(schema(), indent=2)+'\n')
    (out/'tests.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='tests'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--selftest', required=True)
    selftest(parser.parse_args().selftest)
