"""Model-owned category component plus the previously generated bit check.

No category predicate is supplied, selected or corrected by the renderer.
The model selects the category AST and its Boolean composition operator.
Independent sampled classification precedes unchanged native9/full151 gates.
"""
import argparse
import copy
import json
import re
import shutil
from pathlib import Path
from unittest.mock import patch
import research61_ast_feedback as previous

ast=previous.ast;base=ast.base;g=ast.g
SOURCE=previous.SOURCE
ORIGINAL_RUN=base.run
SIGNALS=('instr[6:0]','instr[14:12]','instr_new','rv32e','rv32m')+tuple(f'instr[{i}]' for i in range(32))
OPS=('&&','||','==','!=')


def schema():
    with patch.object(ast.grammar,'SIGNALS',SIGNALS),patch.object(ast.grammar,'BINARY',OPS),patch.object(ast.grammar,'UNARY',('!',)):
        defs=ast.grammar.schema()['$defs']
    return dict(type='object',additionalProperties=False,required=['category','combine','reason'],properties=dict(
        category={'$ref':'#/$defs/expression'},combine=dict(type='string',enum=['&&','||']),reason=dict(type='string')),**{'$defs':defs})


def sample_rows():
    return [r for cohort in ('alignment','history','search') for r in g.read(SOURCE/'v0'/cohort/'result.json')['ledger']]


def observed_inputs(row):
    s=row['sample'];word=s['instruction']
    return {**{f'instr[{i}]':(word>>i)&1 for i in range(32)},'instr[6:0]':word&127,'instr[14:12]':(word>>12)&7,
        'instr_new':s['instr_new'],'rv32e':row['configuration']['RV32E'],'rv32m':row['configuration']['RV32M']}


def evaluate(node,inputs):
    if set(node)=={'signal'}:return inputs[node['signal']]
    if set(node)=={'int'}:return node['int']
    values=[evaluate(x,inputs) for x in node['args']];op=node['op']
    if op=='!':return int(not values[0])
    a,b=values
    if op=='&&':return int(bool(a) and bool(b))
    if op=='||':return int(bool(a) or bool(b))
    if op=='==':return int(a==b)
    if op=='!=':return int(a!=b)
    raise ValueError('category_operator_unsupported')


def validate(value):
    if not isinstance(value,dict) or set(value)!={'category','combine','reason'}:raise ValueError('category_edit_fields')
    if value['combine'] not in ('&&','||') or not isinstance(value['reason'],str):raise ValueError('category_edit_types')
    with patch.object(ast.grammar,'SIGNALS',SIGNALS),patch.object(ast.grammar,'BINARY',OPS),patch.object(ast.grammar,'UNARY',('!',)):
        ast.grammar.expression(value['category'])
    checks=[]
    for row in sample_rows():
        # Independent opcode extraction, not the evaluated candidate predicate.
        # OPCODE_OP=0x33 is confirmed by the original decoder package/ISA rule.
        expected=int(f"{row['sample']['instruction']:032b}"[-7:],2)==0x33
        actual=bool(evaluate(value['category'],observed_inputs(row)))
        checks.append(dict(evidence_id=row['evidence_id'],expected=expected,actual=actual,passed=expected==actual))
    failed=[r for r in checks if not r['passed']]
    return dict(accepted=not failed,checked=len(checks),failed=len(failed),checks=checks,
        scope='Instruction-class classification only, including legal OP with bit28=0. Not native SVA success; full native acceptance follows.')


def composed(value):
    # The payload-check AST is actual prior model output, never a handwritten
    # successful OP predicate. Only model-selected connective/category is added.
    old=g.read(SOURCE/'v0/model_call/model_edit.json')
    if len(old['assertions'])!=1:raise ValueError('expected_single_existing_model_op')
    item=copy.deepcopy(old['assertions'][0])
    item['antecedent']=dict(op=value['combine'],args=[copy.deepcopy(value['category']),item['antecedent']])
    return dict(operation='replace_op',reason=value['reason'],assertions=[item])


def adapt(value,current):
    gate=validate(value)
    if not gate['accepted']:
        raise ValueError(json.dumps(dict(kind='category_applicability_rejected',checked=gate['checked'],failed=gate['failed'],examples=[r for r in gate['checks'] if not r['passed']][:2])))
    return ast.adapt(composed(value),current)


def public_pairs():
    selected={}
    for r in sample_rows():
        s=r['sample'];w=s['instruction'];key=(w&127,(w>>28)&1,s['instr_new'])
        if key in selected:continue
        selected[key]=dict(instruction_hex=f'0x{w:08x}',opcode=w&127,bit28=(w>>28)&1,bit31=(w>>31)&1,
            instr_new=s['instr_new'],expected_illegal=r['expected'],actual_illegal=r['observed'],revision=r['revision'],
            transaction=s['transaction_id'],phase=s['phase'],configuration=r['configuration'])
    return list(selected.values())


def request(prep,feedback,seed):
    req=ast.prior.ORIGINAL_REQUEST(prep,None,seed)
    old=json.loads(req['messages'][1]['content'])
    body={k:old[k] for k in ('case','source','rtl','interface','timing','sampling_semantics')}
    body.update(current_assertions=dict(assertions=[dict(id='a0',preserved_externally=True)]),
        task='Generate ONLY the instruction-class category filter AST for register-register OP. Do not repeat the bit28 test: the existing model-generated bit28 condition is retained separately. Category must include both legal and illegal OP encodings, regardless bit28, funct3, or first/held phase. It must exclude other instruction classes. Select the category operands/constants and the Boolean operator combining it with the retained violation condition. The compiler performs only your requested syntax composition. Return category,combine,reason.',
        public_instruction_class=dict(name='OP (register-register)',opcode_decimal=old['actual_model_op_rule']['opcode'],opcode_signal='instr[6:0]'),
        retained_model_component=dict(source_sha256=g.old.digest(SOURCE/'v0/model_call/model_edit.json'),
            description='Previously generated payload-bit condition and illegal_insn consequent; all420 OP and270 BRANCH detections retained but636 history false alarms. Same-sample timing unchanged.'),
        actual_development_pairs=public_pairs(),output_contract=dict(schema=schema(),signals=SIGNALS),
        acceptance='First validate category against independently decoded instruction classes on all available development samples. Then native first/held12, all9, full115+36 and690 preservation with zero legal false alarms and no critical unknown.',
        actual_feedback=feedback)
    req['messages'][0]['content']='Generate a JSON AST for instruction CLASS membership, not for the payload error. Existing payload checking is already implemented by a prior actual model component. Select every category operand, value and combination operator yourself.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    req['format']=schema();req['options'].update(temperature=0,num_predict=768)
    return req


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    cert=g.prior.prior.native_flow.prior.components(base.P)
    assert cert['actual_op_rule']['opcode']==0x33
    candidate=g.read(SOURCE/'v0/model_call/candidate.json')
    for cohort,n in [('alignment',240),('history',2748),('search',1248)]:
        assert g.prior.diagnostic.audit_native(SOURCE/'v0'/cohort,candidate,base.P,cohort)==n
    # Generic evaluator checks, deliberately not the answer to this category task.
    checks=[]
    for i in range(32):
        row=sample_rows()[0];inputs=observed_inputs(row)
        node=dict(op='==',args=[dict(signal=f'instr[{i}]'),dict(int=inputs[f'instr[{i}]'])])
        assert evaluate(node,inputs)==1;checks.append('bit'+str(i))
    for category in (dict(int=1),dict(int=0),dict(signal='instr[28]')):
        gate=validate(dict(category=category,combine='&&',reason='Local negative fixture, not model output'))
        assert not gate['accepted'];checks.append('invalid_category_rejected')
    req=request(base.P,None,6001)
    assert g.read(base.P/'qualification/local_positive/candidate.json')['assertions'][1]['antecedent'] not in json.dumps(req)
    g.dump(out/'request.preview.json',req);g.dump(out/'checks.json',dict(passed=True,checks=checks,native_records_audited=4236,model_calls=0))
    g.dump(out/'source_hashes.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in [Path(__file__),Path(ast.__file__),SOURCE/'v0/model_call/model_edit.json']})
    print('CATEGORY_PREPARED',len(checks),'checks',flush=True)


def run(out):
    def proxy(folder,iterations,timeout,context_validator):return ORIGINAL_RUN(folder,iterations=2,timeout=timeout,context_validator=context_validator)
    try:
        with patch.object(ast.compact,'request',request),patch.object(base,'run',proxy),patch.object(g.prior.diagnostic,'adapt',adapt),patch.object(g.prior.prior.previous,'novelty',previous.novelty):
            ast.compact.run(out)
    finally:
        if out.exists():
            shutil.copy2(__file__,out/'category_adapter_snapshot.py')
            g.dump(out/'extra_known_rejections.json',ast.prior.previous_rejections()+previous.extra_rejections())
            for p in out.glob('v*/model_call/model_edit.json'):
                try:gate=validate(g.read(p))
                except (ValueError,TypeError,KeyError) as exc:g.dump(p.parent/'category_gate.json',dict(accepted=False,interface_error=str(exc)));continue
                g.dump(p.parent/'category_gate.json',gate)
                if gate['accepted']:
                    combined=composed(g.read(p));g.dump(p.parent/'composed_model_ast.json',combined)
                    g.dump(p.parent/'rendered_edit.json',ast.render(combined))
            protocol=g.read(out/'protocol.json');protocol.update(scope='research62_category_component',maximum_calls=2,
                changes='Category AST and connective are new actual model outputs. Retained bit check/consequent come unchanged from research61 actual model AST. Independent category check precedes unchanged native9/full151 acceptance. Not unrestricted whole-property generation.')
            g.dump(out/'protocol.json',protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    a=p.parse_args();(prepare if a.prepare else run)(a.out.resolve())
