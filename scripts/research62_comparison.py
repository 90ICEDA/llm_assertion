"""Model-selected explicit category comparison, with no implicit truth test.

This interface supports one field/constant comparison, not arbitrary category
expressions. Every field, comparator, integer and connective is model-selected.
The renderer creates the corresponding AST without selecting semantic values.
"""
import argparse
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import research62_category as category

g=category.g;base=category.base;ast=category.ast
COMPARATORS=('==','!=')


def schema():
    return dict(type='object',additionalProperties=False,required=['field','comparison','value','combine','reason'],properties=dict(
        field=dict(type='string',enum=list(category.SIGNALS)),comparison=dict(type='string',enum=list(COMPARATORS)),
        value=dict(type='integer',minimum=0,maximum=2147483647),combine=dict(type='string',enum=['&&','||']),reason=dict(type='string')))


def to_category(value):
    if not isinstance(value,dict) or set(value)!={'field','comparison','value','combine','reason'}:raise ValueError('comparison_fields_required')
    if value['field'] not in category.SIGNALS or value['comparison'] not in COMPARATORS:raise ValueError('comparison_field_or_operator')
    if type(value['value']) is not int or not 0<=value['value']<=2147483647:raise ValueError('comparison_integer_required')
    if value['combine'] not in ('&&','||') or not isinstance(value['reason'],str):raise ValueError('comparison_types')
    return dict(category=dict(op=value['comparison'],args=[dict(signal=value['field']),dict(int=value['value'])]),combine=value['combine'],reason=value['reason'])


def adapt(value,current):return category.adapt(to_category(value),current)


def request(prep,feedback,seed):
    req=category.request(prep,None,seed);body=json.loads(req['messages'][1]['content'])
    body['output_contract']=dict(schema=schema(),scope='One explicit field/constant category comparison. Select every field, comparator, integer and combination operator; the compiler never inserts a missing comparison or changes your chosen value.')
    body['task']='Generate ONLY the instruction-class filter using explicit field,comparison,value,combine,reason. Previous response selected the opcode signal but omitted the comparison, treating every nonzero opcode as true and misclassifying 2304 native records. A correct reason is not an executable comparison. All legal and illegal register-register OP instructions belong to this class; other classes do not. Existing bit-error component and BRANCH protection remain fixed. Select the complete comparison yourself.'
    body['actual_feedback']=dict(source='research62_local_20261023_r01',category_checked=4236,category_failed=2304,
        actual_previous_output=g.read(g.ROOT/'deliverables/research62_local_20261023_r01/v1/model_call/model_edit.json'))
    req['messages'][0]['content']='Return JSON with an explicit field/constant comparison defining instruction-class membership. You must choose all five required fields. The framework renders your choice, then independently checks actual samples and executes original RTL.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'));req['format']=schema()
    return req


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    # Generic syntactic fixtures use deliberately wrong values/categories;
    # never present the correct category expression as a fixture or prompt.
    for field in category.SIGNALS:
        for comparison in COMPARATORS:
            for combine in ('&&','||'):
                v=dict(field=field,comparison=comparison,value=17,combine=combine,reason='syntax fixture')
                tree=to_category(v)
                assert tree['category']['args']==[dict(signal=field),dict(int=17)] and tree['category']['op']==comparison and tree['combine']==combine
                checks.append([field,comparison,combine])
    for v in ({},dict(field='instr[32]',comparison='==',value=17,combine='&&',reason='bad'),dict(field='instr[6:0]',comparison='==',value=True,combine='&&',reason='bad')):
        try:to_category(v)
        except ValueError:pass
        else:raise AssertionError('bad fixture accepted')
    req=request(base.P,None,6001)
    assert g.read(base.P/'qualification/local_positive/candidate.json')['assertions'][1]['antecedent'] not in json.dumps(req)
    g.dump(out/'request.preview.json',req);g.dump(out/'checks.json',dict(passed=True,syntax_choices_preserved=len(checks),invalid_cases_rejected=3,model_calls=0))
    g.dump(out/'source_hashes.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in [Path(__file__),Path(category.__file__)]})
    print('COMPARISON_PREPARED',len(checks)+3,'checks',flush=True)


def run(out):
    try:
        with patch.object(ast.compact,'request',request),patch.object(g.prior.diagnostic,'adapt',adapt),patch.object(g.prior.prior.previous,'novelty',category.previous.novelty):
            ast.compact.run(out)
    finally:
        if out.exists():
            shutil.copy2(__file__,out/'comparison_adapter_snapshot.py')
            g.dump(out/'extra_known_rejections.json',ast.prior.previous_rejections()+category.previous.extra_rejections())
            for p in out.glob('v*/model_call/model_edit.json'):
                try:converted=to_category(g.read(p));gate=category.validate(converted)
                except (ValueError,TypeError,KeyError) as exc:g.dump(p.parent/'category_gate.json',dict(accepted=False,interface_error=str(exc)));continue
                g.dump(p.parent/'category_gate.json',gate);g.dump(p.parent/'category_ast.json',converted)
                if gate['accepted']:
                    combined=category.composed(converted);g.dump(p.parent/'composed_model_ast.json',combined)
                    g.dump(p.parent/'rendered_edit.json',ast.render(combined))
            protocol=g.read(out/'protocol.json');protocol.update(scope='research62_explicit_category_comparison',maximum_calls=1,
                changes='One real model-selected field/comparator/integer/connective. Syntax-only conversion to category AST and composition with existing real model bit-check. Original category/native9/full151 gates unchanged. No semantic operand completion.')
            g.dump(out/'protocol.json',protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    a=p.parse_args();(prepare if a.prepare else run)(a.out.resolve())
