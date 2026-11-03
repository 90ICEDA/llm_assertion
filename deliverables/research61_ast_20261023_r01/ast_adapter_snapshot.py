"""Bounded local AST generation reusing the existing syntax-only renderer.

All bits, operators and timing are model choices. No semantic correction or
successful OP expression is included in the request or rendering code.
"""
import argparse
import copy
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import research17_model_schema as grammar
import research61_contrast_refine as prior

base=prior.base;compact=prior.compact;g=prior.g
SIGNALS=('instr','illegal_insn','instr_new','rv32e','rv32m','instr[6:0]','instr[14:12]')+tuple(f'instr[{i}]' for i in range(32))
ORIGINAL_ADAPT=g.prior.diagnostic.adapt


def schema():
    with patch.object(grammar,'SIGNALS',SIGNALS):expr=grammar.schema()['$defs']
    s=copy.deepcopy(base.SCHEMA);s['$defs']=expr
    for side in ('antecedent','consequent'):s['properties']['assertions']['items']['properties'][side]={'$ref':'#/$defs/expression'}
    return s


def render(value):
    v=copy.deepcopy(value)
    if not isinstance(v,dict) or not isinstance(v.get('assertions'),list):raise ValueError('Expected assertion list')
    with patch.object(grammar,'SIGNALS',SIGNALS):
        for i,a in enumerate(v['assertions']):
            for side in ('antecedent','consequent'):
                a[side]=grammar.expression(a[side],f'$.assertions[{i}].{side}')
    return v


def adapt(value,current):return ORIGINAL_ADAPT(render(value),current)


def op_pairs():
    # Collapse only genuinely identical first/held observations, never assume
    # a held phase has the same output as its first sample.
    groups={}
    for row in prior.decoded_table():
        if row['fields']['opcode']!=51:continue
        key=json.dumps([row['transaction'],row['instruction_hex'],row['fields'],row['observations']],sort_keys=True)
        group=groups.setdefault(key,{k:copy.deepcopy(row[k]) for k in ('transaction','instruction_hex','fields','observations')})
        group.setdefault('sample_ids',[]).extend(row['sample_ids'])
        group.setdefault('phase_and_instr_new',[]).append(dict(phases=row['phases'],instr_new=row['instr_new']))
    return list(groups.values())


def request(prep,feedback,seed):
    req=prior.ORIGINAL_REQUEST(prep,None,seed)
    body=json.loads(req['messages'][1]['content'])
    # The preserved BRANCH text is not a template for OP; compilation still
    # copies the actual previously generated BRANCH property unchanged.
    body['current_assertions']=dict(assertions=[dict(id='a0',preserved_externally=True)])
    body['confirmed_obligations']={'op_bit28_illegal':body['confirmed_obligations']['op_bit28_illegal']}
    body.pop('native_development_samples')
    body['actual_feedback']=feedback
    body['op_development_pairs']=op_pairs()
    body['output_contract']=dict(schema=schema(),allowed_signals=SIGNALS,
        syntax='Expression is exactly {signal:string}, {int:integer}, or {op:string,args:[expressions]}. Choose every operand/operator/constant; never output text expressions. Renderer only adds parentheses.')
    body['task']='Generate a new OP property from the actual verified model OP rule and measured legal/illegal pairs. Previous model proposals tested unrelated funct3 conditions and wrongly failed legal instructions. Do not imitate them or BRANCH conditions. Preserve all first and held targets and avoid all legal false alarms. BRANCH is fixed outside this task and is still checked by native replay. Return model-owned AST operands and timing; no successful predicate is supplied.'
    req['messages'][0]['content']='Return one JSON edit containing AST expressions for OP hardware assertions. Every operand and timing must implement the confirmed OP obligation. No raw expression strings. The original RTL and real development observations determine the semantics.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    req['format']=schema();req['options'].update(temperature=0,num_predict=1024)
    return req


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    # Syntax/transport checks use arbitrary operators/indices, not a success
    # assertion; the model never receives these fixtures.
    checks=[]
    for i in range(32):
        with patch.object(grammar,'SIGNALS',SIGNALS):
            text=grammar.expression(dict(signal=f'instr[{i}]'))
        assert text==f'instr[{i}]';checks.append(f'bit_{i}_unchanged')
    with patch.object(grammar,'SIGNALS',SIGNALS):
        for bad in ({'signal':'instr[32]'}, {'signal':'opcode'}, {'int':True}, 'instr[28]'):
            try:grammar.expression(bad)
            except grammar.SchemaError:checks.append('invalid_rejected')
            else:raise AssertionError('invalid accepted')
    public=op_pairs();original=[r for r in prior.decoded_table() if r['fields']['opcode']==51]
    assert sum(len(x['sample_ids']) for x in public)==sum(len(x['sample_ids']) for x in original)
    req=request(base.P,None,6001)
    assert g.read(base.P/'qualification/local_positive/candidate.json')['assertions'][1]['antecedent'] not in json.dumps(req)
    g.dump(out/'request.preview.json',req);g.dump(out/'checks.json',dict(passed=True,checks=checks,first_held_groups=len(public)))
    g.dump(out/'source_hashes.json',{Path(p).relative_to(g.ROOT).as_posix():g.old.digest(Path(p)) for p in (__file__,prior.__file__,grammar.__file__)})
    print('AST_PREPARED',len(checks),'checks',flush=True)


def run(out):
    try:
        with patch.object(compact,'request',request),patch.object(g.prior.diagnostic,'adapt',adapt),patch.object(g.prior.prior.previous,'novelty',prior.novelty):
            compact.run(out)
    finally:
        if out.exists():
            shutil.copy2(__file__,out/'ast_adapter_snapshot.py')
            g.dump(out/'extra_known_rejections.json',prior.previous_rejections())
            for p in out.glob('v*/model_call/model_edit.json'):
                try:rendered=render(g.read(p))
                except (ValueError,TypeError,KeyError):continue
                g.dump(p.parent/'rendered_edit.json',rendered)
            protocol=g.read(out/'protocol.json');protocol.update(scope='research61_local_ast',maximum_calls=1,
                changes='One real local model AST generation, syntax-only rendering via research17. All32 bit selections available; fixed BRANCH omitted from prompt but copied unchanged into native candidate. Full original9/151 acceptance retained.')
            g.dump(out/'protocol.json',protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    a=p.parse_args();(prepare if a.prepare else run)(a.out.resolve())
