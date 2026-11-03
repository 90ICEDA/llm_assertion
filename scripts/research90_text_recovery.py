"""Two-call text-expression recovery pilot, unchanged native R0/R1 acceptance.

New protocol after failed research87, not extra calls charged to its budget.
No plan-to-predicate synthesis, successful archive reuse, or manual repair.
"""
import argparse
import copy
import json
import secrets
import shutil
import time
from pathlib import Path
from unittest.mock import patch
import research87_cross_parent_recovery as x

ROOT,read,dump,sha=x.ROOT,x.read,x.dump,x.sha
PREVIOUS=ROOT/'deliverables/research87_prepare_20261025_r01'
TRIAL=ROOT/'deliverables/research87_real_20261025_r01'
SEED=9007
TEXT_ADAPT=x.ast.ORIGINAL_ADAPT


def schema():
    return copy.deepcopy(x.ast.base.SCHEMA)


def request(candidate,feedback,iteration):
    prior=read(PREVIOUS/'request.preview.json')
    src=json.loads(prior['messages'][1]['content'])
    body={k:src[k] for k in ('case','source','rtl','confirmed_obligations','interface','timing','sampling_semantics','actual_model_op_rule')}
    body.update(current_op=[a for a in candidate['assertions'] if a['obligations']==['op_bit28_illegal']],
        fixed_component='The already generated BRANCH property is copied unchanged outside this edit and checked in all replays.',
        actual_feedback=feedback,
        task='Repair the actual OP property to eliminate the measured false alarms without losing any OP detection. Generate the entire antecedent, consequent and timing yourself as SystemVerilog expression strings. The confirmed rule applies to OP, not other instruction classes, on first and held samples. The consequent must check the required hardware response. The compiler adds only implication syntax; it does not correct operands, constants or bit indices.',
        output_contract='Return exactly operation,reason,assertions. operation=replace_op. Each assertion has antecedent and consequent strings, timing same_sample or next_sample, obligations=[op_bit28_illegal]. No AST objects, declarations or clock wrapper. Allowed signals: instr, instr_new, illegal_insn, rv32e, rv32m. Bits/slices and standard Boolean comparisons are supported.',
        acceptance='Same native current9 first/held12, search36 and history115. Full420 OP and270 BRANCH, zero false alarms, critical unknown, misses or required-untriggered samples. Max2 calls; no retry or interface change during this trial.')
    # These are measured development records. No independent data or successful
    # property is read. Include both target and legal controls, not only failures.
    result=read(PREVIOUS/'qualification/alignment/result.json')
    selected={}
    for r in result['ledger']:
        s=r['sample'];w=s['instruction']
        key=(w&127,(w>>28)&1,s['instr_new'],r['revision'],r['expected'],r['observed'])
        if key not in selected:
            selected[key]=dict(instruction=f'{w:08x}',opcode_decimal=w&127,bit28=(w>>28)&1,
                instr_new=s['instr_new'],phase=s['phase'],revision=r['revision'],
                configuration=r['configuration'],expected_illegal=r['expected'],actual_illegal=r['observed'],
                evidence_id=r['evidence_id'])
    body['measured_development_controls']=list(selected.values())
    req=copy.deepcopy(prior)
    req.update(format=schema(),messages=[dict(role='system',content='Generate a JSON SVA edit using textual SystemVerilog expressions. Apply the confirmed obligation to the original RTL and real development observations. Every predicate must come from your response; explanations alone are not executable protection.'),dict(role='user',content=json.dumps(body,separators=(',',':')))])
    req['options'].update(seed=SEED+iteration,temperature=0.2,num_predict=1536)
    return req


def independent(prep,out,versions):
    freeze=dict(time=time.time(),versions={a:x.old.acceptance.sha(c) for a,c in versions.items()},
        source_sha256=read(prep/'source_binding.json')['source_sha256'],development_exclusion_sha256=sha(prep/'excluded_words.json'))
    for arm,c in versions.items():dump(out/'frozen'/arm/'candidate.json',c)
    dump(out/'freeze.json',freeze)
    seed=secrets.randbits(63);txns=x.holdout.base.generate(seed,read(prep/'excluded_words.json'))
    dump(out/'independent_cases.json',txns)
    dump(out/'generation.json',dict(seed=seed,at=time.time(),freeze_sha256=sha(out/'freeze.json')))
    results={}
    for arm,c in versions.items():
        folder=out/'frozen'/arm
        dump(folder/'independent_cases.json',txns)
        for rev in ('before','after'):shutil.copytree(prep/rev,folder/rev)
        result=x.old.replay(c,txns,'independent',folder/'independent',folder,configs=x.holdout.base.CONFIGS)
        dump(folder/'tool_config.json',dict(version=read(folder/'independent/before/result.json')['tool_version']))
        if result['healthy']:
            dump(folder/'audit.json',x.holdout.base.native_audit(folder,result))
            with patch.object(x.old,'CONFIGS',x.holdout.base.CONFIGS):guard=x.all_guard(folder/'independent',result,c)
            summary=x.holdout.summarize(result,guard)
        else:summary=dict(passed=False,counts=result['counts'],status='native_failure')
        dump(folder/'summary.json',summary);results[arm]=summary
        assert x.old.acceptance.sha(read(folder/'candidate.json'))==freeze['versions'][arm]
        print('INDEPENDENT90',arm,summary['passed'],summary['counts'],flush=True)
    dump(out/'independent_summary.json',results)


def prepare(out):
    x.verify(PREVIOUS);out.mkdir(parents=True,exist_ok=False)
    names=('initial.json','proposal.json','baseline_full.json','source_binding.json','qualification.json','initial_feedback.json','history_cases.json','search_cases.json')
    for name in names:shutil.copy2(PREVIOUS/name,out/name)
    for rev in ('before','after'):shutil.copytree(PREVIOUS/rev,out/rev)
    exclusions=set(read(PREVIOUS/'excluded_words.json'))
    exclusions.update(t['instruction'] for t in read(TRIAL/'independent_cases.json'))
    dump(out/'excluded_words.json',sorted(exclusions))
    protocol=read(PREVIOUS/'protocol.json')
    protocol.update(created=time.time(),name='research90_text_expression_recovery',seeds=[SEED,SEED+1],
        interface='Existing textual-expression frontend; the real model owns all OP predicates. Same text interface in both rounds, no staged plan. BRANCH unchanged.',
        selection='Same already observed research61 proposal, fixed R0/R1. New recovery pilot after failed research87; not a prospective new-case prevalence study.',
        comparison='Presentation differs from research87 and is not credited to history gating. Ordinary stops on its original R0 acceptance. Same two-call ceiling; actual ordinary continuation0 and history at most2.',
        terminal='Freeze both arms after recovery stops; generate96 new words excluding prior inputs including research87. Prior independent outcomes are not used for model feedback or rule changes.',
        prior_budget='research87 exhausted2/2 and remains failed. This separate pilot has a newly sealed2-call local budget, not a retroactive extension.')
    protocol['budget'].update(maximum_native_compiles=16,maximum_native_executes=16)
    dump(out/'protocol.json',protocol)
    req=request(read(out/'proposal.json'),read(out/'initial_feedback.json'),0)
    dump(out/'request.preview.json',req)
    # Syntax-only preservation and reject tests, never model candidates.
    current=read(out/'initial.json');checks=[]
    for index in (0,7,19,31):
        value=dict(operation='replace_op',reason='local interface fixture only',assertions=[dict(
            antecedent=f'instr[{index}]',consequent='illegal_insn',timing='same_sample',obligations=['op_bit28_illegal'])])
        c,_=TEXT_ADAPT(value,current)
        assert c['assertions'][1]['antecedent']==value['assertions'][0]['antecedent']
        assert c['assertions'][0]==current['assertions'][0];checks.append(f'bit{index}_preserved')
    for change in ('ast','missing','branch'):
        bad=copy.deepcopy(value)
        if change=='ast':bad['assertions'][0]['antecedent']={'signal':'instr[7]'}
        if change=='missing':del bad['assertions'][0]['timing']
        if change=='branch':bad['assertions'][0]['obligations']=['illegal_branch_persists']
        try:TEXT_ADAPT(bad,current)
        except (ValueError,TypeError,KeyError,AssertionError):checks.append(change+'_rejected')
        else:raise AssertionError(change)
    dump(out/'checks.json',dict(passed=True,checks=checks,tests_not_sent_to_model=True))
    reused=[PREVIOUS/n for n in names]+[PREVIOUS/'qualification/decision.json',PREVIOUS/'qualification/alignment/result.json']
    dump(out/'reused_bindings.json',{p.relative_to(ROOT).as_posix():sha(p) for p in reused})
    dump(out/'code_versions.json',{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.relative_to(out).as_posix():sha(p) for p in list(out.glob('*.json'))+list(out.glob('before/*.sv'))+list(out.glob('after/*.sv'))})
    print('PREPARED90',len(checks),'checks; max2 local calls',flush=True)


def run(prep,out):
    for name,h in read(prep/'reused_bindings.json').items():assert sha(ROOT/name)==h,name
    with patch.object(x,'request',request),patch.object(x.ast,'adapt',TEXT_ADAPT),patch.object(x,'independent',independent):
        x.run(prep,out)
    cost=read(out/'cost.json')['total']
    assert cost['model_calls']<=2 and cost['native_compile_calls']<=16 and cost['native_execute_calls']<=16


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve())
