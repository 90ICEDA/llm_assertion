"""Program-decoded native samples; model-owned rules and applicability, then SVA.

Reuses the research52 bounded campaign with explicit adapter hooks. No old result
is relabelled. Correct local fixtures never become model plans or SVA proposals.
"""
import argparse
import copy
import json
import shutil
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import research52_ibex_bit_gate as prior

ROOT=prior.ROOT
read,dump=prior.read,prior.dump
P52=ROOT/'deliverables/research52_prepare_20261022_r02'
R52=ROOT/'deliverables/research52_real_20261022_r01'
BASE_SOURCE_CHECK=prior.source_check
OB=prior.old.OBLIGATIONS


def decoded(w):
    word=int(w['instruction_hex'],16)
    return dict(id=w['id'],instruction_hex=w['instruction_hex'],
        sample={k:w[k] for k in ('sample_id','transaction_id','phase','instr_new','configuration')},
        decoded=dict(opcode=word&127,funct3=(word>>12)&7,bit28=bool(word&(1<<28)),bit31=bool(word&(1<<31))),
        measured=dict(before_illegal=bool(w['before_illegal']),after_illegal=bool(w['after_illegal'])))


def source_check(prep):
    expected=BASE_SOURCE_CHECK(prep)
    public=[decoded(w) for w in read(prep/'windows.public.json')]
    assert read(prep/'decoded.public.json')==public,'decoded_samples_changed'
    return dict(public=public,expected=expected)


def rule_evaluate(rules,w):
    def phase(rule):
        return rule['phase']=='every_sample' or (rule['phase']=='new_only' and w['sample']['instr_new']==1) or (rule['phase']=='held_only' and w['sample']['instr_new']==0)
    b=rules['illegal_branch_persists'];o=rules['op_bit28_illegal'];d=w['decoded'];word=int(w['instruction_hex'],16)
    return sorted(ob for ob,applies in (
        ('illegal_branch_persists',d['opcode']==b['opcode'] and d['funct3'] in b['funct3_values'] and phase(b)),
        ('op_bit28_illegal',d['opcode']==o['opcode'] and bool(word&(1<<o['bit_index']))==o['bit_value'] and phase(o))) if applies)


def validate(value,context):
    reasons=[]
    if not isinstance(value,dict) or set(value)!={'rules','windows'} or not isinstance(value['rules'],dict) or set(value['rules'])!=set(OB) or not isinstance(value['windows'],list):
        return dict(accepted=False,reasons=[dict(kind='plan_schema')])
    b=value['rules']['illegal_branch_persists'];o=value['rules']['op_bit28_illegal']
    phases={'every_sample','new_only','held_only'}
    wellformed=(isinstance(b,dict) and set(b)=={'opcode','funct3_values','phase'} and
        isinstance(o,dict) and set(o)=={'opcode','bit_index','bit_value','phase'})
    if wellformed:
        wellformed=(type(b['opcode']) is int and type(o['opcode']) is int and
            type(o['bit_index']) is int and 0<=o['bit_index']<32 and type(o['bit_value']) is bool and
            isinstance(b['funct3_values'],list) and all(type(x) is int and 0<=x<8 for x in b['funct3_values']) and
            len(set(b['funct3_values']))==len(b['funct3_values']) and
            type(b['phase']) is str and b['phase'] in phases and type(o['phase']) is str and o['phase'] in phases)
    if not wellformed:reasons.append(dict(kind='rule_schema'))
    else:
        # Checked against the confirmed contract, not against candidate SVA.
        if not (b['opcode']==0x63 and sorted(b['funct3_values'])==[2,3] and b['phase']=='every_sample'):
            reasons.append(dict(kind='branch_rule_disagrees_with_confirmed_spec'))
        if not (o['opcode']==0x33 and o['bit_index']==28 and o['bit_value'] is True and o['phase']=='every_sample'):
            reasons.append(dict(kind='op_rule_disagrees_with_confirmed_spec'))
    expected={w['id']:sorted(ob for ob,applies in [('illegal_branch_persists',w['branch_applicable']),('op_bit28_illegal',w['op_applicable'])] if applies) for w in context['expected']['windows']}
    public={w['id']:w for w in context['public']};seen=set()
    if not expected or set(expected)!=set(public):reasons.append(dict(kind='invalid_sample_inventory'))
    for row in value['windows']:
        if not isinstance(row,dict) or set(row)!={'id','obligations'} or type(row['id']) is not str or row['id'] not in public or row['id'] in seen:
            reasons.append(dict(kind='invalid_or_duplicate_sample_reference'));continue
        ident=row['id'];seen.add(ident);labels=row['obligations']
        if not isinstance(labels,list) or not all(type(x) is str and x in OB for x in labels) or len(set(labels))!=len(labels):
            reasons.append(dict(kind='label_schema',id=ident));continue
        if sorted(labels)!=expected[ident]:reasons.append(dict(kind='incorrect_sample_applicability',id=ident,actual=labels))
        if wellformed and sorted(labels)!=rule_evaluate(value['rules'],public[ident]):
            reasons.append(dict(kind='rule_label_inconsistency',id=ident,actual=labels))
    if seen!=set(expected):reasons.append(dict(kind='incomplete_sample_inventory'))
    return dict(accepted=not reasons,reasons=reasons,windows=len(expected),
        scope='Program supplied decoded fields; model rules and labels checked against original native development samples and confirmed spec. Not autonomous model decoding or SVA acceptance.')


def verified_plan(prep,plan,verdict):
    actual=validate(plan,source_check(prep))
    if not actual['accepted'] or actual!=verdict:raise ValueError('decoded_plan_not_accepted')
    return copy.deepcopy(plan)


def plan_payload(prep,feedback=None):
    req=prior.old.payload(prep,phase='decoded_sample_rule_selection')
    body=json.loads(req['messages'][1]['content'])
    for k in ('output','limits','timing'):body.pop(k)
    body['windows']=read(prep/'decoded.public.json')
    body['data_roles']='Decoded fields are deterministic program measurements bound to original native samples, not model answers. Select conditions from confirmed obligations, then label each id. RTL outputs are observations, not applicability labels. An obligation applies even when the original RTL satisfies it. Do not copy or recompute the sample fields.'
    body['output']=dict(rules=dict(illegal_branch_persists=dict(opcode='integer',funct3_values=['integer values'],phase='every_sample | new_only | held_only'),
        op_bit28_illegal=dict(opcode='integer',bit_index='integer 0..31',bit_value='boolean',phase='every_sample | new_only | held_only')),
        windows=[dict(id='given id',obligations=['zero or more applicable obligation IDs; empty array when neither applies'])])
    body['actual_development_feedback']=feedback
    body['limits']='Return exactly rules and windows. No SVA in this phase. Cover all12 IDs once. Your labels must agree with your rules AND the confirmed specification. No predicates or labels are corrected by the checker.'
    req['messages'][0]['content']='Select repair-obligation rules and classify bound native development samples using the supplied program-decoded fields. Return only the declared JSON.'
    req['messages'][1]['content']=json.dumps(body);req.update(seed=5301,max_tokens=3072)
    return req


def sva_payload(prep,plan,verdict,current,feedback):
    verified=verified_plan(prep,plan,verdict)
    req=prior.old.payload(prep,current,feedback,'refinement_after_verified_decoded_applicability')
    body=json.loads(req['messages'][1]['content'])
    body['verified_model_plan']=verified;body['bound_decoded_samples']=read(prep/'decoded.public.json')
    body['plan_scope']='Model-selected rules and applicability passed independent checking; bit decoding was supplied by the program. Generate SVA yourself. The framework does not translate rules to properties. Native target/history checks still decide acceptance.'
    req['messages'][1]['content']=json.dumps(body);req['seed']=5301
    return req


class Model(prior.Model):
    def __init__(self,out,prep):
        super().__init__(out,prep);self.config['options'].update(seed=5301,num_predict=3072)
        cfg=read(out/'remote_transport_config.json');cfg.update(max_output_tokens=3072,max_output_tokens_by_stage=dict(plan=3072,sva=2048));dump(out/'remote_transport_config.json',cfg)
        self.output_kind='rules_and_applicability_on_program_decoded_samples'
    def _payload(self,current,target,feedback,phase):
        if self.stage=='plan':
            self.config['options']['num_predict']=3072
            return plan_payload(self.prep,feedback)
        if self.stage!='sva':raise ValueError('unknown_stage')
        self.config['options']['num_predict']=2048
        return sva_payload(self.prep,self.plan,self.verdict,current,feedback)
    def save_decoded_output(self,folder,value,current,secret):
        if self.stage=='plan':
            verdict=validate(value,source_check(self.prep));dump(folder/'plan_gate.json',verdict);dump(folder/'model_plan.json',value)
            return value,'plan_accepted' if verdict['accepted'] else 'plan_rejected'
        return super().save_decoded_output(folder,value,current,secret)


def fixture(context):
    return dict(rules=dict(illegal_branch_persists=dict(opcode=99,funct3_values=[2,3],phase='every_sample'),
        op_bit28_illegal=dict(opcode=51,bit_index=28,bit_value=True,phase='every_sample')),
        windows=[dict(id=w['id'],obligations=sorted(ob for ob,applies in [('illegal_branch_persists',w['branch_applicable']),('op_bit28_illegal',w['op_applicable'])] if applies)) for w in context['expected']['windows']])


def qualify(prep):
    context=source_check(prep);good=fixture(context);checks=[]
    def test(name,value,want=False):
        verdict=validate(value,context);assert verdict['accepted']==want,name
        if not want:
            try:verified_plan(prep,value,dict(accepted=True))
            except ValueError:pass
            else:raise AssertionError('failed_plan_unlocked:'+name)
        checks.append(dict(name=name,passed=True))
    test('local_fixture_only_not_model_response',good,True)
    for ob,field,replacements in [('op_bit28_illegal','bit_index',[31,True,28.0,-1,32,None]),
            ('op_bit28_illegal','bit_value',[False,1,None]),('op_bit28_illegal','opcode',[99,True,None]),
            ('illegal_branch_persists','opcode',[51,True,None]),('illegal_branch_persists','funct3_values',[[6],[2],[2,2],[True,3],None])]:
        for value in replacements:
            bad=copy.deepcopy(good);bad['rules'][ob][field]=value;test(f'{ob}:{field}:{value}',bad)
    for ob in OB:
        for phase in ('new_only','held_only',None):
            bad=copy.deepcopy(good);bad['rules'][ob]['phase']=phase;test(ob+':wrong_phase:'+str(phase),bad)
        for field in good['rules'][ob]:
            bad=copy.deepcopy(good);bad['rules'][ob].pop(field);test(ob+':missing:'+field,bad)
    for i,row in enumerate(good['windows']):
        for labels in ([x for x in OB if x not in row['obligations']],None,['unknown'],[True]):
            bad=copy.deepcopy(good);bad['windows'][i]['obligations']=labels;test(f'{i}:wrong_labels:{labels}',bad)
        bad=copy.deepcopy(good);bad['windows'][i]['id']='absent';test(f'{i}:wrong_sample',bad)
    for key in ('rules','windows'):
        bad=copy.deepcopy(good);bad.pop(key);test('missing:'+key,bad)
    bad=copy.deepcopy(good);bad['windows'].append(copy.deepcopy(good['windows'][0]));test('duplicate_window',bad)
    bad=copy.deepcopy(good);bad['windows'].pop();test('missing_window',bad)
    # Correct labels cannot conceal incorrect model rules; self-consistency alone cannot override spec.
    bad=copy.deepcopy(good);bad['rules']['op_bit28_illegal']['bit_index']=31
    bad['windows']=[dict(id=w['id'],obligations=rule_evaluate(bad['rules'],w)) for w in context['public']]
    test('self_consistent_wrong_rule_rejected',bad)
    for index in (0,1):
        old_plan=read(R52/f'plan/v{index}/model_call/model_plan.json')
        projected=copy.deepcopy(good)
        projected['windows']=[dict(id=w['id'],obligations=sorted(ob for ob,on in [('illegal_branch_persists',w['branch_applicable']),('op_bit28_illegal',w['op_applicable'])] if on)) for w in old_plan['windows']]
        test(f'archived_model_wrong_labels_still_rejected_v{index}',projected)
    verified_plan(prep,good,validate(good,context))
    for w in context['public']:
        bits=f"{int(w['instruction_hex'],16):032b}";d=w['decoded']
        assert d==dict(opcode=int(bits[-7:],2),funct3=int(bits[-15:-12],2),bit28=bits[3]=='1',bit31=bits[0]=='1')
    checks.append(dict(name='independent_binary_slice_crosscheck',passed=True))
    bad=copy.deepcopy(read(prep/'decoded.public.json'));bad[0]['decoded']['opcode']^=1
    original_read=read
    def corrupt(path):return bad if Path(path).name=='decoded.public.json' else original_read(path)
    with patch(__name__+'.read',side_effect=corrupt):
        try:verified_plan(prep,good,validate(good,context))
        except AssertionError:checks.append(dict(name='tampered_program_decode_blocks_sva',passed=True))
        else:raise AssertionError('tampered_decode_allowed')
    return dict(passed=True,checks=checks,model_calls=0,scope='Local interface controls only; no generated SVA.')


def native_decode_check(prep):
    windows=read(prep/'decoded.public.json')
    source=['module tb; logic [31:0] instr; initial begin']
    for w in windows:
        source.extend([f"instr=32'h{w['instruction_hex'][2:]}; #1;",f'$display("DECODE {w["id"]} %0d %0d %0d %0d",instr[6:0],instr[14:12],instr[28],instr[31]);'])
    source+=['$display("NATIVE_RUN_COMPLETE"); $finish; end endmodule']
    folder=prep/'decode_native';result=prior.old.native.run_native('\n'.join(source),folder)
    assert result['compile_status']=='passed' and result['execution_status']=='completed'
    observed={}
    for line in (folder/'execute.log').read_text().splitlines():
        if line.startswith('DECODE '):
            _,ident,op,f3,b28,b31=line.split();assert ident not in observed
            observed[ident]=dict(opcode=int(op),funct3=int(f3),bit28=bool(int(b28)),bit31=bool(int(b31)))
    assert observed=={w['id']:w['decoded'] for w in windows}
    dump(prep/'decode_check.json',dict(passed=True,samples=len(windows),model_calls=0,
        scope='Native SystemVerilog bit-extraction crosscheck only. No DUT property evaluation or model success claim. Original DUT replay reused by hash.'))


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    for n,h in read(P52/'sealed.json').items():assert prior.old.digest(P52/n)==h,n
    for rev in ('before','after'):shutil.copytree(P52/rev,out/rev)
    names=('windows.public.json','expected.private.json','native_binding.json','shared_initial.json','source_binding.json',
        'history_cases.json','search_cases.json','development_manifest.json','baseline_full.json')
    for name in names:shutil.copy2(P52/name,out/name)
    for cohort in ('history','search'):
        dump(out/f'baseline/{cohort}/result.json',read(P52/f'baseline/{cohort}/result.json'))
    dump(out/'baseline_reuse.json',dict(source=P52.relative_to(ROOT).as_posix(),sealed_sha256=prior.old.digest(P52/'sealed.json'),
        actual_native_source='deliverables/research52_prepare_20261022_r01/baseline',new_dut_replays=0))
    dump(out/'decoded.public.json',[decoded(w) for w in read(out/'windows.public.json')])
    source_check(out);native_decode_check(out);dump(out/'qualification.json',qualify(out))
    dump(out/'plan_request.preview.json',plan_payload(out))
    dump(out/'protocol.json',dict(scope='research53_program_decode_then_model_rules_sva',max_calls=4,plan_max_calls=2,sva_max_calls=2,
        endpoint=prior.old.DEFAULT_URL,model=prior.old.DEFAULT_MODEL,retries=0,
        plan_request_sha256=prior.old.digest(out/'plan_request.preview.json'),
        information_change='Program supplies decoded input fields; model selects rules and labels. Not comparable to autonomous bit decoding accuracy in research52.',
        acceptance='Independent spec rules and all12 labels agree, then native151 development transactions:420 OP violations repaired,270 BRANCH detections retained, no FP/unknown/required missing trigger.',
        rules_are_not_translated_to_sva=True,independent_test='not part of this task'))
    snap=out/'source_snapshot';snap.mkdir()
    for p in [Path(__file__),*[ROOT/'scripts'/n for n in read(P52/'source_hashes.json')]]:shutil.copy2(p,snap/p.name)
    dump(out/'source_hashes.json',{p.name:prior.old.digest(p) for p in snap.iterdir()})
    dump(out/'cost.json',prior.old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():prior.old.digest(p) for p in out.rglob('*') if p.is_file() and p.suffix in ('.json','.sv','.py')})
    print('DECODED_PREPARED',len(read(out/'qualification.json')['checks']),flush=True)


def run(prep,out,auth):
    # Reuse the audited two-plan/two-SVA workflow; only the declared interface
    # implementation changes. This is not mocking a model or native execution.
    with ExitStack() as stack:
        for name,value in [('Model',Model),('source_check',source_check),('validate',validate)]:
            stack.enter_context(patch.object(prior,name,value))
        prior.run(prep,out,auth)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path);a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
