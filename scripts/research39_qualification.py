"""Prospective AST syntax and native transport controls, NOT model repairs."""
import argparse
import copy
from pathlib import Path

import research17_loop as loop
import research17_model_schema as grammar
import research39_ast_refinement as adapter
from research34_campaign import snapshot

read, dump = loop.read, loop.dump


def qualify(out):
    loop.prepare(out)
    snapshot(out)
    current = read(adapter.previous.PREP/'shared_initial.json')
    # Arbitrary transport fixture, deliberately NOT a solution to stall hold.
    # Native failures below are expected and are not accepted repair evidence.
    fixture = dict(operation='replace_one', assertion_id='a2', reason='syntax transport fixture only',
        assertions=[dict(antecedent={'signal':'svalid'},
            consequent={'op':'||','args':[{'signal':'mready'},{'signal':'mvalid'}]},
            timing='next_sample', obligation=['stall_stability'])])
    checks = []
    def check(name, condition):
        checks.append(dict(name=name,passed=bool(condition)))
        assert condition, name
    def reject(name, value, code):
        try: adapter.assemble(value,current)
        except grammar.SchemaError as exc:
            check(name, exc.code == code)
            return
        raise AssertionError(name+': unexpected acceptance')
    candidate = adapter.assemble(fixture, current)
    check('only_selected_slot_replaced', all(a == b for a,b in zip(candidate['assertions'],current['assertions']) if a['id'] != 'a2'))
    rendered = adapter.render_edit(fixture,current)
    check('no_predicate_inference', rendered['assertions'][0]['antecedent'] == 'svalid' and
          rendered['assertions'][0]['consequent'] == '(mready || mvalid)')
    for name, value, code in (
        ('reset_is_not_property_signal', {'signal':'rst'}, 'unknown_signal'),
        ('clock_is_not_property_signal', {'signal':'clk'}, 'unknown_signal'),
        ('raw_text_rejected', 'svalid', 'expression_object_required'),
        ('bare_arrow_rejected', {'op':'=>','args':[{'signal':'svalid'},{'signal':'mvalid'}]}, 'unsupported_operator'),
        ('temporal_arrow_rejected', {'op':'|=>','args':[{'signal':'svalid'},{'signal':'mvalid'}]}, 'unsupported_operator'),
        ('wrong_arity', {'op':'!','args':[]}, 'operator_arity'),
        ('bool_literal_rejected', {'int':True}, 'integer_out_of_range')):
        bad = copy.deepcopy(fixture)
        bad['assertions'][0]['antecedent'] = value
        reject(name,bad,code)
    for name, field, value, code in (
        ('wrong_obligation_slot','assertion_id','a0','target_slot'),
        ('keep_rejected','operation','keep','operation')):
        bad=copy.deepcopy(fixture);bad[field]=value;reject(name,bad,code)
    for name in grammar.UNARY:
        tree={'op':name,'args':[{'signal':'sdata'}]}
        check('unary_'+name, bool(grammar.expression(tree)))
    for name in grammar.BINARY:
        tree={'op':name,'args':[{'signal':'sdata'},{'int':2}]}
        check('binary_'+name, grammar.expression(tree) == '(sdata '+name+' 2)')
    # Specific prior real errors must survive; no native samples disappear.
    old_call = read(loop.ROOT/'deliverables/research38_real_20261022_r01/core/v1/model_call/result.json')
    prior = read(loop.ROOT/'deliverables/research38_prepare_20261022_r03/development_diagnostics.json')
    next_feedback = adapter.feedback(None,dict(accepted=False,reasons=[dict(kind='model_output_unusable')]),old_call,prior)
    check('actual_interface_error_preserved', next_feedback['interface_diagnostic']['candidate_error'] == old_call['candidate_error'])
    check('numeric_history_preserved_after_no_native', next_feedback['prior_native_development_diagnostics'] == prior)
    dump(out/'feedback_replay.json',next_feedback)
    dump(out/'fixture.json',fixture)
    dump(out/'rendered_fixture.json',rendered)
    dump(out/'schema.json',adapter.schema(current))
    try:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(adapter.schema(current))
        jsonschema.validate(fixture,adapter.schema(current))
        check('recursive_schema_valid',True)
    except ImportError:
        dump(out/'jsonschema_status.json',dict(status='unavailable'))
    # Actually compile both timing selections and execute the same legal FIFO
    # input. These arbitrary fixtures are kept out of all repair prompts.
    for timing in ('same_sample','next_sample'):
        value=copy.deepcopy(fixture);value['assertions'][0]['timing']=timing
        c=adapter.assemble(value,current)
        case=loop.common_case()
        build=loop.runtime.build(c,out/timing/'compile',2,0)
        check(timing+':native_compile',build['native']['compile_status']=='passed')
        record=loop.runtime.execute(build,out/timing/'correct',case['rows'],'correct')
        check(timing+':native_execution',record['native']['execution_status']=='completed')
        check(timing+':sampling',record['sampling_qualification']['status']=='passed')
        dump(out/timing/'native_diagnostic.json',dict(native=record['native'],
            scope='Arbitrary AST transport fixture. Not model output, not a semantic repair success.'))
    from research17_report import artifacts,cost_audit
    cost=cost_audit(out,artifacts(out));dump(out/'cost.json',cost)
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,model_calls=0,
        qualification_only=True,scope='Schema rendering and actual native transport only; no repair acceptance or independent testing.',cost=cost['total'])
    dump(out/'verification.json',result)
    print('AST_QUALIFICATION',len(checks),result['passed'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();assert loop.ROOT in a.out.resolve().parents
    qualify(a.out.resolve())
