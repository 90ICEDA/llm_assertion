"""One real AST refinement from newly measured full-history false alarms."""
import argparse
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import research61_ast_local as ast

g=ast.g;SOURCE=g.ROOT/'deliverables/research61_ast_20261023_r01'
ORIGINAL_REQUEST=ast.request


def representatives():
    history=g.read(SOURCE/'v0/history/result.json');selected={}
    for r in history['ledger']:
        if r['expected']!=0 or r['observed']!=0 or not any(a['failed'] for a in r['native']['assertions']):continue
        s=r['sample'];w=s['instruction'];key=(w&127,s['instr_new'])
        if key in selected:continue
        selected[key]=dict(sample=s,configuration=r['configuration'],revision=r['revision'],
            fields=dict(opcode=w&127,bit28=(w>>28)&1,bit31=(w>>31)&1,funct3=(w>>12)&7),
            expected_illegal=r['expected'],actual_illegal=r['observed'],native_assertions=r['native']['assertions'])
    assert selected
    return list(selected.values())


def extra_rejections():
    return [dict(source=(SOURCE/'v0/model_call/candidate.json').as_posix(),signature=g.prior.prior.previous.op_signature(g.read(SOURCE/'v0/model_call/candidate.json')))]


def novelty(candidate,known):return ast.prior.ORIGINAL_NOVELTY(candidate,known+ast.prior.previous_rejections()+extra_rejections())


def request(prep,feedback,seed):
    req=ORIGINAL_REQUEST(prep,None,seed)
    body=json.loads(req['messages'][1]['content'])
    body['actual_feedback']=dict(actual_model_ast=g.read(SOURCE/'v0/model_call/model_edit.json'),
        small_gate=g.read(SOURCE/'v0/alignment/focus_gate.json')['phases'],
        history_counts=g.read(SOURCE/'v0/history/result.json')['counts'],
        search_counts=g.read(SOURCE/'v0/search/result.json')['counts'],
        target_preservation=g.read(SOURCE/'v0/decision.json')['target_preservation'],
        actual_legal_false_alarms=representatives())
    body['task']='Refine your actual AST. It now detects all first/held OP targets, but native history replay found legal false alarms on other instruction classes. Use the actual decoded false alarms and confirmed OP rule to correct applicability. Maintain all 420 OP and 270 BRANCH detections. Do not weaken the consequent or condition on illegal_insn to hide failures. You must select every Boolean operator, operand, value and timing. Keep all original acceptance checks; output only OP AST.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    return req


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    candidate=g.read(SOURCE/'v0/model_call/candidate.json')
    for cohort,n in [('alignment',240),('history',2748),('search',1248)]:
        assert g.prior.diagnostic.audit_native(SOURCE/'v0'/cohort,candidate,ast.base.P,cohort)==n
    assert not novelty(candidate,[])['accepted']
    req=request(ast.base.P,None,6001)
    assert g.read(ast.base.P/'qualification/local_positive/candidate.json')['assertions'][1]['antecedent'] not in json.dumps(req)
    g.dump(out/'request.preview.json',req);g.dump(out/'false_alarm_representatives.json',representatives())
    g.dump(out/'checks.json',dict(passed=True,native_records_audited=4236,repeated_failed_ast_rejected=True,remote_calls=0))
    print('HISTORY_FEEDBACK_PREPARED',len(representatives()),'actual representatives',flush=True)


def run(out):
    try:
        with patch.object(ast,'request',request),patch.object(ast.prior,'novelty',novelty):ast.run(out)
    finally:
        if out.exists():
            shutil.copy2(__file__,out/'ast_feedback_snapshot.py')
            g.dump(out/'feedback_rejections.json',extra_rejections())
            g.dump(out/'feedback_representatives.json',representatives())
            files=[SOURCE/'v0/model_call/model_edit.json',SOURCE/'v0/model_call/candidate.json',SOURCE/'v0/history/result.json',SOURCE/'v0/search/result.json',SOURCE/'v0/decision.json']
            g.dump(out/'feedback_sources.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in files})
            protocol=g.read(out/'protocol.json');protocol['changes']='One real local AST refinement from actual full151 false alarms; all original acceptance checks retained. No independent test used.'
            g.dump(out/'protocol.json',protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    a=p.parse_args();(prepare if a.prepare else run)(a.out.resolve())
