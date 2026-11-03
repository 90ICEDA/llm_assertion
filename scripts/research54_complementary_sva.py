"""Prospective OP-only synthesis with an immutable, measured BRANCH component.

Research53's whole plan remains rejected. This protocol independently certifies
only its actual OP judgment and fixes the original model's measured BRANCH SVA.
No OP property is manufactured from the rule or substituted for model output.
"""
import argparse
import copy
import json
import re
import shutil
from pathlib import Path
import research53_decoded_applicability as previous

ROOT=previous.ROOT
old=previous.prior.old
common=previous.prior
read,dump=previous.read,previous.dump
P53=ROOT/'deliverables/research53_prepare_20261022_r01'
R53=ROOT/'deliverables/research53_real_20261023_r01'


def op_check(plan,context):
    reasons=[]
    try:
        r=plan['rules']['op_bit28_illegal']
        if not (set(r)=={'opcode','bit_index','bit_value','phase'} and type(r['opcode']) is int and r['opcode']==51 and
                type(r['bit_index']) is int and r['bit_index']==28 and r['bit_value'] is True and r['phase']=='every_sample'):
            reasons.append('op_rule_not_confirmed')
        expected={w['id']:w['op_applicable'] for w in context['expected']['windows']}
        rows=plan['windows'];seen=set()
        for w in rows:
            ident=w['id'];labels=w['obligations']
            if ident in seen or ident not in expected or not isinstance(labels,list) or not all(x in old.OBLIGATIONS for x in labels) or len(set(labels))!=len(labels):
                reasons.append('invalid_sample_or_labels');continue
            seen.add(ident)
            if ('op_bit28_illegal' in labels)!=expected[ident]:reasons.append('op_sample_applicability_incorrect:'+ident)
        if seen!=set(expected):reasons.append('missing_op_sample_judgment')
    except (TypeError,KeyError):reasons.append('op_plan_schema')
    return dict(accepted=not reasons,reasons=reasons,scope='OP rule and OP membership on12 bound development samples only. Entire research53 plan remains rejected.')


def components(prep):
    for path,h in read(prep/'component_binding.json')['files'].items():assert old.digest(ROOT/path)==h,path
    context=previous.source_check(prep)
    plan=read(R53/'plan/v1/model_call/model_plan.json')
    raw=json.loads(read(R53/'plan/v1/model_call/response.assembled.json')['message']['content'])
    assert raw==plan,'not_actual_model_plan'
    original=previous.validate(plan,context)
    assert original==read(R53/'plan/v1/decision.json') and not original['accepted'],'old_failure_changed'
    op=op_check(plan,context);assert op['accepted'],op
    initial=read(prep/'shared_initial.json')
    assert initial==read(common.R51/'v1/model_call/candidate.json')
    assert read(prep/'protected_branch.json')==initial['assertions'][0]
    baseline=read(prep/'baseline_full.json');rows=[r for r in baseline['ledger'] if r['obligation']=='illegal_branch_persists']
    projected=copy.deepcopy(rows)
    for row in projected:row['native']['assertions']=[a for a in row['native']['assertions'] if a['id']=='a0']
    info=old.acceptance.inspect(projected)
    assert len(info['detections'])==270 and not any(info[k] for k in ('unknown','misses','false_positives','errors'))
    assert all(r['evidence_id'] in info['triggers'] for r in projected if r['required'])
    assert not old.admissible(baseline),'baseline_whole_set_is_not_accepted'
    return dict(actual_op_rule=plan['rules']['op_bit28_illegal'],actual_op_membership=[dict(id=w['id'],applicable='op_bit28_illegal' in w['obligations']) for w in plan['windows']],
        op_certificate=op,branch_detections_retained=270,branch_trigger_rows=len(info['triggers']),
        original_plan_verdict=original,scope='Prospective component decomposition, not retrospective acceptance of research53.')


def assemble(value,current):
    assert isinstance(value,dict) and set(value)=={'operation','reason','assertions'} and value['operation']=='replace_op'
    assert 1<=len(value['assertions'])<=3
    assert all(a.get('obligations')==['op_bit28_illegal'] for a in value['assertions'])
    parsed=old.assemble({**value,'operation':'replace'},None)
    branch=copy.deepcopy(current['assertions'][0]);assert branch['obligations']==['illegal_branch_persists']
    for index,a in enumerate(parsed['assertions'],1):a['id']=f'a{index}'
    return dict(assertions=[branch]+parsed['assertions'])


def all_property_guard(result,natives,candidate):
    """A false alarm counts even outside the property-declared obligation."""
    references={(r['sample_id'],old.CONFIGS.index(r['configuration'])):r for r in result['reference']}
    allowed={a['id'] for a in candidate['assertions']};false_alarms=[];unknown=[]
    for rev,native in natives.items():
        if native['compile_status']!='passed' or native['execution_status']!='completed':
            unknown.append(dict(revision=rev,kind='native_unavailable'));continue
        for fail in native['failures']:
            ident=re.fullmatch(r'(a\d+)_c(\d+)',fail['id']);cycle=re.search(r'cycle=(-?\d+)',fail['detail'])
            if not ident or not cycle or ident[1] not in allowed:
                unknown.append(dict(revision=rev,kind='unattributed_failure',failure=fail));continue
            ref=references.get((int(cycle[1]),int(ident[2])))
            if ref is None:
                unknown.append(dict(revision=rev,kind='unbound_failure',failure=fail));continue
            if ref['actual']['after']!=ref['expected']:
                unknown.append(dict(revision=rev,kind='fixed_reference_disagrees',failure=fail));continue
            if ref['actual'][rev]==ref['expected']:
                false_alarms.append(dict(revision=rev,assertion=ident[1],sample_id=int(cycle[1]),configuration=ref['configuration']))
    return dict(accepted=not false_alarms and not unknown,false_alarms=false_alarms,unknown=unknown,
        scope='All native property failures, regardless of claimed obligation mapping.')


def payload(prep,current,feedback=None):
    cert=components(prep);req=old.payload(prep,current,feedback,'complementary_op_synthesis')
    body=json.loads(req['messages'][1]['content'])
    body['component_contract']='The existing a0 BRANCH property is immutable and already protects its270 observed violations. Generate only replacement OP properties. The framework copies a0 unchanged and adds your exact OP predicates; it never converts a plan into SVA. Entire research53 plan was rejected, but its OP rule and OP sample membership were independently correct. Full151-transaction native acceptance remains mandatory.'
    body['actual_model_op_rule']=cert['actual_op_rule'];body['actual_model_op_membership']=cert['actual_op_membership']
    body['bound_decoded_samples']=read(prep/'decoded.public.json')
    body['output']=dict(operation='replace_op',reason='explanation string',assertions=[dict(antecedent='boolean SystemVerilog expression',consequent='boolean SystemVerilog expression',timing='same_sample | next_sample',obligations=['op_bit28_illegal'])])
    body['limits']='JSON only. Exactly operation,reason,assertions. operation=replace_op;1..3 OP properties; each obligations=[op_bit28_illegal]. Choose predicates and timing yourself. Only signals instr,instr_new,illegal_insn,rv32m,rv32e and supported sampled functions. No declarations or edits to a0. Unchanged rejected OP predicates are refused.'
    req['messages'][1]['content']=json.dumps(body);req['seed']=5401
    return req


class Model(old.Model):
    def __init__(self,out,prep):
        super().__init__(out,prep);self.config['max_model_calls']=2;self.config['options']['seed']=5401
    def _payload(self,current,target,feedback,phase):return payload(self.prep,current,feedback)
    def save_decoded_output(self,folder,value,current,secret):
        candidate=assemble(value,current)
        assert candidate['assertions'][0]==read(self.prep/'protected_branch.json')
        duplicate=common.duplicates(candidate,current,'replace');dump(folder/'duplicate_gate.json',duplicate)
        dump(folder/'candidate.json',candidate);(folder/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n')
        return (candidate,'exact_model_op_plus_immutable_model_branch') if duplicate['accepted'] else (None,'unchanged_or_duplicate_rejected')


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    for n,h in read(P53/'sealed.json').items():assert old.digest(P53/n)==h
    for rev in ('before','after'):shutil.copytree(P53/rev,out/rev)
    for name in ('windows.public.json','decoded.public.json','expected.private.json','native_binding.json','shared_initial.json','source_binding.json','history_cases.json','search_cases.json','development_manifest.json','baseline_full.json'):
        shutil.copy2(P53/name,out/name)
    for c in ('history','search'):dump(out/f'baseline/{c}/result.json',read(P53/f'baseline/{c}/result.json'))
    dump(out/'protected_branch.json',read(out/'shared_initial.json')['assertions'][0])
    sources=[R53/'plan/v1'/name for name in ('decision.json','model_call/model_plan.json','model_call/response.assembled.json','model_call/response.stream.raw')]
    sources += [common.R51/'v1/model_call/candidate.json',P53/'baseline_full.json']
    dump(out/'component_binding.json',dict(files={p.relative_to(ROOT).as_posix():old.digest(p) for p in sources}))
    cert=components(out);dump(out/'component_certificate.json',cert)
    context=previous.source_check(out);plan=read(R53/'plan/v1/model_call/model_plan.json');checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    check('actual_op_component_valid',op_check(plan,context)['accepted'])
    check('whole_plan_still_rejected',not previous.validate(plan,context)['accepted'])
    for bit in (31,True,None):
        bad=copy.deepcopy(plan);bad['rules']['op_bit28_illegal']['bit_index']=bit;check('wrong_op_bit:'+str(bit),not op_check(bad,context)['accepted'])
    for i in range(12):
        bad=copy.deepcopy(plan);row=bad['windows'][i]
        row['obligations']=[x for x in row['obligations'] if x!='op_bit28_illegal'] if 'op_bit28_illegal' in row['obligations'] else row['obligations']+['op_bit28_illegal']
        check('wrong_op_label:'+str(i),not op_check(bad,context)['accepted'])
    current=read(out/'shared_initial.json')
    repeated=read(common.R51/'v2/model_call/model_edit.json');repeated['operation']='replace_op'
    candidate=assemble(repeated,current)
    check('original_branch_copied_exactly',candidate['assertions'][0]==current['assertions'][0])
    check('actual_bad_op_predicate_not_rewritten',candidate['assertions'][1]['antecedent']==repeated['assertions'][0]['antecedent'])
    check('repeated_failed_op_rejected',not common.duplicates(candidate,current,'replace')['accepted'])
    bad=copy.deepcopy(repeated);bad['assertions'][0]['obligations']=['illegal_branch_persists']
    try:assemble(bad,current)
    except AssertionError:check('model_cannot_replace_protected_branch',True)
    else:raise AssertionError('branch_modification_allowed')
    measured=read(P53/'baseline/search/result.json')
    natives={rev:read(common.R51/f'v1/search/{rev}/result.json') for rev in ('before','after')}
    check('actual_baseline_all_property_guard',all_property_guard(measured,natives,current)['accepted'])
    injected=copy.deepcopy(natives)
    injected['after']['failures'].append(dict(id='a1_c0',detail='cycle=0'))
    check('local_cross_obligation_false_alarm_fixture_rejected',not all_property_guard(measured,injected,current)['accepted'])
    injected=copy.deepcopy(natives);injected['after']['failures'].append(dict(id='a1_c0',detail='cycle=99999'))
    check('local_unbound_failure_fixture_unknown_rejected',not all_property_guard(measured,injected,current)['accepted'])
    dump(out/'qualification.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,scope='Component/interface checks on existing measured development evidence, not new model output.'))
    feedback=dict(history=old.evidence(read(out/'baseline/history/result.json')),search=old.evidence(read(out/'baseline/search/result.json')))
    dump(out/'initial_feedback.json',feedback);dump(out/'request.preview.json',payload(out,current,feedback))
    dump(out/'protocol.json',dict(scope='research54_immutable_branch_model_op',maximum_calls=2,retries=0,
        endpoint=old.DEFAULT_URL,model=old.DEFAULT_MODEL,request_sha256=old.digest(out/'request.preview.json'),
        acceptance='Same151 native development transactions: repair420 OP misses; retain270 BRANCH detections; no FP/critical unknown/required missing trigger.',
        whole_research53_plan_remains_rejected=True,only_actual_op_subjudgment_reused=True,immutable_branch_is_original_model_output=True,
        independent_test='Not generated in this task; separate after acceptance.'))
    snap=out/'source_snapshot';snap.mkdir()
    for p in [Path(__file__),*[ROOT/'scripts'/n for n in read(P53/'source_hashes.json')]]:shutil.copy2(p,snap/p.name)
    dump(out/'source_hashes.json',{p.name:old.digest(p) for p in snap.iterdir()})
    dump(out/'sealed.json',{p.relative_to(out).as_posix():old.digest(p) for p in out.rglob('*') if p.is_file() and p.suffix in ('.py','.sv','.json')})
    print('COMPLEMENT_PREPARED',len(checks),'checks; no new model/native calls',flush=True)


def run(prep,out,auth_path):
    auth=read(auth_path);protocol=read(prep/'protocol.json')
    assert auth['scope']==protocol['scope'] and auth['authorized_calls']==2 and auth['endpoint']==protocol['endpoint']
    assert auth['request_sha256']==protocol['request_sha256'] and auth['run_output']==out.relative_to(ROOT).as_posix()
    for n,h in read(prep/'sealed.json').items():assert old.digest(prep/n)==h,n
    for n,h in read(prep/'source_hashes.json').items():assert old.digest(ROOT/'scripts'/n)==h,n
    components(prep);out.mkdir(parents=True,exist_ok=False);shutil.copy2(auth_path,out/'authorization.json');shutil.copytree(prep/'source_snapshot',out/'source_snapshot')
    dump(out/'protocol.json',protocol);model=Model(out,prep);decisions=[];accepted=None
    current=read(prep/'shared_initial.json');baseline=read(prep/'baseline_full.json');feedback=read(prep/'initial_feedback.json')
    try:
        for i in range(2):
            folder=out/f'v{i}';call,candidate=model.call(folder/'model_call',current,'op_bit28_illegal',feedback,'complementary_sva')
            if candidate is None:
                decision=dict(accepted=False,reasons=[dict(kind='unusable_or_duplicate_proposal')])
                feedback=dict(previous_native_feedback=feedback,call=call,decision=decision)
            else:
                h=old.replay(candidate,read(prep/'history_cases.json'),'history',folder/'history',prep)
                s=old.replay(candidate,read(prep/'search_cases.json'),'search',folder/'search',prep)
                decision=old.decide(baseline,common.combine(h,s))
                assert candidate['assertions'][0]==read(prep/'protected_branch.json')
                guards={cohort:all_property_guard(result,{rev:read(folder/cohort/rev/'result.json') for rev in ('before','after')},candidate) for cohort,result in [('history',h),('search',s)]}
                dump(folder/'all_property_guard.json',guards)
                for cohort,guard in guards.items():
                    if not guard['accepted']:
                        decision['accepted']=False;decision['reasons'].append(dict(kind='all_property_false_alarm_or_unknown',cohort=cohort,details=guard))
                dump(folder/'mapping.json',dict(history=h['mapping'],search=s['mapping']))
                feedback=dict(actual_proposal=candidate,history=old.evidence(h),search=old.evidence(s),decision=common.gate_feedback(decision))
                if decision['accepted']:
                    accepted=candidate;dump(out/'accepted_candidate.json',candidate)
                    dump(out/'acceptance.json',dict(sha256=old.acceptance.sha(candidate),history=h['counts'],search=s['counts'],decision=decision))
            dump(folder/'decision.json',decision);decisions.append(dict(version=i,accepted=decision['accepted']))
            print('COMPLEMENT_VERSION',i,decision['accepted'],flush=True)
            if accepted is not None:break
    finally:
        dump(out/'outcome.json',dict(status='accepted_development_only' if accepted else 'no_accepted_sva',calls=len(model.calls),decisions=decisions,
            accepted_candidate_sha256=old.acceptance.sha(accepted) if accepted else None,independent_test='not_run',formal_calls=0))
        dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path);a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
