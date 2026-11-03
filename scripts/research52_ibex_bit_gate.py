"""Ibex166: verified model bitfield plan before native SVA refinement.

Preparation performs local checks/replays only. Real calls need a new bounded
grant. Archived research51 records and its failed decisions are immutable.
"""
import argparse
import copy
import json
import re
import shutil
from pathlib import Path
import research51_history_loop as old

ROOT=old.ROOT
P51=ROOT/'deliverables/research51_prepare_20261022_r02'
R51=ROOT/'deliverables/research51_real_20261022_r01'
read,dump=old.read,old.dump
FIELDS={'id','sample_id','transaction_id','phase','instr_new','opcode','funct3','bit28','bit31',
        'before_illegal','after_illegal','branch_applicable','op_applicable'}
BOOLS={'bit28','bit31','before_illegal','after_illegal','branch_applicable','op_applicable'}


def trace(path):
    rows={}
    for line in path.read_text().splitlines():
        if not line.startswith('TRACE '):continue
        f=dict(x.split('=') for x in line.split()[1:]);sid=int(f['sample'])
        assert sid not in rows,'duplicate_native_sample'
        rows[sid]=f
    return rows


def truth(window):
    """Independent bit decoding, never inferred from the candidate assertion."""
    word=int(window['instruction_hex'],16);op=word&127;f3=(word>>12)&7
    return dict(id=window['id'],sample_id=window['sample_id'],transaction_id=window['transaction_id'],
        phase=window['phase'],instr_new=window['instr_new'],opcode=op,funct3=f3,
        bit28=bool(word&(1<<28)),bit31=bool(word&(1<<31)),
        before_illegal=bool(window['before_illegal']),after_illegal=bool(window['after_illegal']),
        branch_applicable=op==0x63 and f3 in (2,3),op_applicable=op==0x33 and bool(word&(1<<28)))


def source_check(prep):
    binding=read(prep/'native_binding.json')
    for name,sha in binding['files'].items():
        assert old.digest(ROOT/name)==sha,'changed_native_source:'+name
    base=R51/'v1/search';samples=read(base/'samples.json')
    traces={rev:trace(base/rev/'execute.log') for rev in ('before','after')}
    for w in read(prep/'windows.public.json'):
        s=samples[w['sample_id']];ci=old.CONFIGS.index(w['configuration'])
        assert int(w['instruction_hex'],16)==s['instruction']
        assert all(w[k]==s[k] for k in ('sample_id','transaction_id','phase','instr_new'))
        for rev in traces:
            f=traces[rev][s['sample_id']]
            assert int(f['instr'],16)==s['instruction'] and int(f['new'])==s['instr_new']
            assert int(f['txn'])==s['transaction_id'] and int(f['phase'])==s['phase']
            assert ((int(f['observed'],2)>>ci)&1)==w[rev+'_illegal']
        assert w['after_illegal']==old.historical.oracle(s['instruction'],s['instr_new'],w['configuration'])
    expected=dict(op_illegal_bit=28,windows=[truth(w) for w in read(prep/'windows.public.json')])
    assert read(prep/'expected.private.json')==expected,'changed_private_answer'
    return expected


def validate(value,expected):
    reasons=[]
    if not isinstance(value,dict) or set(value)!={'op_illegal_bit','windows'} or not isinstance(value.get('windows'),list):
        return dict(accepted=False,reasons=[dict(kind='plan_schema')])
    if type(value['op_illegal_bit']) is not int or value['op_illegal_bit']!=expected['op_illegal_bit']:
        reasons.append(dict(kind='incorrect_obligation_bit',field='op_illegal_bit',actual=value['op_illegal_bit']))
    known={w['id']:w for w in expected['windows']};seen=set()
    if not known:reasons.append(dict(kind='empty_expected_inventory'))
    for w in value['windows']:
        if not isinstance(w,dict) or set(w)!=FIELDS:
            reasons.append(dict(kind='window_schema'));continue
        ident=w['id']
        if type(ident) is not str or ident not in known or ident in seen:
            reasons.append(dict(kind='unknown_or_duplicate_window'));continue
        seen.add(ident)
        for k in sorted(FIELDS-{'id'}):
            want=bool if k in BOOLS else int
            if type(w[k]) is not want or w[k]!=known[ident][k]:
                reasons.append(dict(kind='incorrect_sample_field',id=ident,field=k,actual=w[k]))
    if seen!=set(known):reasons.append(dict(kind='incomplete_window_inventory'))
    return dict(accepted=not reasons,reasons=reasons,windows=len(known),
        scope='Development-native sample bindings and independent encoding applicability only; not SVA acceptance.')


def verified_plan(prep,plan,verdict):
    actual=validate(plan,source_check(prep))
    if not actual['accepted'] or actual!=verdict:raise ValueError('plan_not_independently_accepted')
    return copy.deepcopy(plan)


def signature(a):
    # Text-equivalent only; do not claim general logical equivalence checking.
    clean=lambda x:old.native.unparen(re.sub(r'\s+','',x))
    return clean(a['antecedent']),clean(a['consequent']),a['timing']


def duplicates(candidate,current,operation):
    previous={signature(a) for a in (current or {}).get('assertions',[])};seen=set();reasons=[]
    for i,a in enumerate(candidate['assertions']):
        sig=signature(a)
        if sig in seen:reasons.append(dict(kind='duplicate_property',assertion=a['id']))
        seen.add(sig)
        if operation=='add' and i>=len((current or {}).get('assertions',[])) and sig in previous:
            reasons.append(dict(kind='repeated_added_property',assertion=a['id']))
    if current and {signature(a) for a in candidate['assertions']}==previous:
        reasons.append(dict(kind='unchanged_rejected_baseline_predicates'))
    return dict(accepted=not reasons,reasons=reasons,scope='Whitespace and enclosing-parenthesis normalization only; no semantic rewriting.')


def combine(h,s):
    return dict(healthy=h['healthy'] and s['healthy'],ledger=h['ledger']+s['ledger'],
        counts={k:h['counts'][k]+s['counts'][k] for k in h['counts']},required_untriggered=h['required_untriggered']+s['required_untriggered'])


def gate_feedback(verdict):
    """Bound diagnostics, preserving full decisions locally instead of truncating RTL."""
    return dict(accepted=verdict['accepted'],reasons=[
        {**{k:v for k,v in r.items() if k!='evidence_keys'},
         **(dict(evidence_count=len(r['evidence_keys']),representative_evidence_keys=r['evidence_keys'][:2]) if 'evidence_keys' in r else {})}
        for r in verdict['reasons']],
        scope='Actual gate reasons; full evidence-key lists and mapping remain in local decision.json.')


def plan_payload(prep,feedback=None):
    req=old.payload(prep,phase='bitfield_applicability_judgment')
    body=json.loads(req['messages'][1]['content']);body.pop('output')
    body.pop('limits');body['current_assertions']=None
    body['windows']=read(prep/'windows.public.json')
    body['output']=dict(op_illegal_bit='integer bit index named by the confirmed OP obligation',windows=[dict(
        id='provided id',sample_id='integer',transaction_id='integer',phase='integer',instr_new='integer 0 or 1',
        opcode='integer value of instruction bits6:0',funct3='integer bits14:12',bit28='boolean',bit31='boolean',
        before_illegal='boolean from before output at this sample',after_illegal='boolean from after output at this sample',
        branch_applicable='boolean: confirmed BRANCH obligation applies on this sample',
        op_applicable='boolean: confirmed OP obligation applies on this sample')])
    body['limits']='Return only this JSON. Every field binds to its named sample. Decode instruction bits yourself. Applicability is from specification, never from the candidate alarm or whether the old RTL failed. Do not generate SVA. No fields are corrected by the validator.'
    body['actual_development_feedback']=feedback
    req['messages'][0]['content']='Identify bitfields and obligation applicability on original historical RTL development samples. Return the declared JSON only; do not generate assertions.'
    req['messages'][1]['content']=json.dumps(body);req.update(seed=5201,max_tokens=4096)
    return req


def sva_payload(prep,plan,verdict,current,feedback):
    checked=verified_plan(prep,plan,verdict)
    req=old.payload(prep,current,feedback,'refinement_after_verified_bitfield_plan')
    body=json.loads(req['messages'][1]['content'])
    body['verified_model_plan']=checked
    body['plan_scope']='Actual model fields independently verified against original native development samples. Not a proof. Preserve historical BRANCH protection and resolve actual OP misses. Unchanged/duplicate predicates are rejected before compilation.'
    req['messages'][1]['content']=json.dumps(body);req['seed']=5201
    return req


class Model(old.Model):
    def __init__(self,out,prep):
        super().__init__(out,prep);self.config['max_model_calls']=4
        self.config['options'].update(seed=5201,num_predict=4096)
        self.stage='plan';self.output_kind='bitfield_applicability_plan';self.plan=None;self.verdict=None
        cfg=read(out/'remote_transport_config.json');cfg.update(max_output_tokens=4096,max_output_tokens_by_stage=dict(plan=4096,sva=2048));dump(out/'remote_transport_config.json',cfg)
    def _payload(self,current,target,feedback,phase):
        if self.stage=='plan':
            self.config['options']['num_predict']=4096
            return plan_payload(self.prep,feedback)
        if self.stage!='sva':raise ValueError('unknown_stage')
        self.config['options']['num_predict']=2048
        return sva_payload(self.prep,self.plan,self.verdict,current,feedback)
    def save_decoded_output(self,folder,value,current,secret):
        if self.stage=='plan':
            gate=validate(value,source_check(self.prep));dump(folder/'plan_gate.json',gate);dump(folder/'model_plan.json',value)
            return value,'plan_accepted' if gate['accepted'] else 'plan_rejected'
        candidate=old.assemble(value,current)
        duplicate=duplicates(candidate,current,value['operation']);dump(folder/'duplicate_gate.json',duplicate)
        dump(folder/'candidate.json',candidate)
        (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n')
        return (candidate,'assembled_without_semantic_rewrite') if duplicate['accepted'] else (None,'duplicate_rejected_before_native')


def qualify(prep):
    expected=source_check(prep);checks=[]
    def test(name,value,want=False):
        actual=validate(value,expected);assert actual['accepted']==want,name
        if not want:
            # Deliberately forged acceptance cannot bypass independent validation.
            try:verified_plan(prep,value,dict(accepted=True))
            except ValueError:pass
            else:raise AssertionError('failed_plan_unlocked:'+name)
        checks.append(dict(name=name,passed=True))
    test('local_oracle_fixture_not_a_model_response',expected,True)
    for bit in (31,True,28.0,None):
        bad=copy.deepcopy(expected);bad['op_illegal_bit']=bit;test('wrong_bit_or_type:'+repr(bit),bad)
    for i,w in enumerate(expected['windows']):
        for k in FIELDS-{'id'}:
            bad=copy.deepcopy(expected);bad['windows'][i][k]=not w[k] if k in BOOLS else w[k]+1
            test(f'{i}:wrong:{k}',bad)
            bad=copy.deepcopy(expected);bad['windows'][i].pop(k);test(f'{i}:missing:{k}',bad)
        for k in BOOLS:
            bad=copy.deepcopy(expected);bad['windows'][i][k]=int(w[k]);test(f'{i}:nonboolean:{k}',bad)
    for kind in ('missing_window','duplicate_window','unknown_id','missing_top_field'):
        bad=copy.deepcopy(expected)
        if kind=='missing_window':bad['windows'].pop()
        elif kind=='duplicate_window':bad['windows'].append(copy.deepcopy(bad['windows'][0]))
        elif kind=='unknown_id':bad['windows'][0]['id']='absent'
        else:bad.pop('op_illegal_bit')
        test(kind,bad)
    for value in (None,[],dict(op_illegal_bit=28,windows=[None])):test('malformed:'+repr(value),value)
    for field in ('sample_id','transaction_id','phase','instr_new','opcode','funct3'):
        bad=copy.deepcopy(expected);bad['windows'][0][field]=float(bad['windows'][0][field])
        test('noninteger:'+field,bad)
    stale=validate(expected,expected);stale['accepted']=False
    try:verified_plan(prep,expected,stale)
    except ValueError:checks.append(dict(name='stale_verdict_cannot_unlock',passed=True))
    else:raise AssertionError('stale_verdict')
    current=read(prep/'shared_initial.json');edit=read(R51/'v2/model_call/model_edit.json')
    repeated=old.assemble(edit,current)
    assert not duplicates(repeated,current,'add')['accepted'];checks.append(dict(name='actual_research51_duplicate_rejected',passed=True))
    spaced=copy.deepcopy(repeated);spaced['assertions'][-1]['antecedent']=' ( '+spaced['assertions'][-1]['antecedent']+' ) '
    assert not duplicates(spaced,current,'add')['accepted'];checks.append(dict(name='whitespace_parentheses_duplicate_rejected',passed=True))
    local_fixture=copy.deepcopy(edit);local_fixture['assertions'][0]['antecedent']="instr[6:0] == 7'h33 && instr[28]"
    assert duplicates(old.assemble(local_fixture,current),current,'add')['accepted']
    checks.append(dict(name='distinct_local_fixture_allowed_only_to_native_gate_not_model_success',passed=True))
    assert not old.admissible(read(prep/'baseline_full.json'))
    checks.append(dict(name='passing_plan_does_not_accept_failing_native_sva',passed=True))
    template=sva_payload(prep,expected,validate(expected,expected),current,None)
    assert json.loads(template['messages'][1]['content'])['verified_model_plan']==expected
    # This test payload is never saved/sent; the actual SVA payload requires a real plan.
    checks.append(dict(name='fixture_unlocked_only_local_payload_no_remote',passed=True))
    diagnostic=gate_feedback(old.decide(read(prep/'baseline_full.json'),read(prep/'baseline_full.json')))
    assert len(json.dumps(diagnostic))<5000 and not diagnostic['accepted']
    checks.append(dict(name='bounded_actual_feedback_keeps_unresolved_failure',passed=True))
    return dict(passed=True,checks=checks,model_calls=0,fixtures_are_not_model_outputs=True)


def prepare(out,reuse=None):
    out.mkdir(parents=True,exist_ok=False)
    for name,sha in read(P51/'sealed.json').items():assert old.digest(P51/name)==sha
    for rev in ('before','after'):shutil.copytree(P51/rev,out/rev)
    for name in ('source_binding.json','history_cases.json','search_cases.json','development_manifest.json'):
        shutil.copy2(P51/name,out/name)
    shutil.copy2(R51/'v1/model_call/candidate.json',out/'shared_initial.json')
    result=read(R51/'v1/search/result.json');refs=result['reference'];windows=[]
    for ci in range(3):
        for family in ('branch_reserved','op_bit28','branch_legal','op_control'):
            if ci and family not in ('op_bit28','op_control'):continue
            for initial in ((True,False) if ci==0 else (False,)):
                r=next(r for r in refs if r['family']==family and r['configuration']==old.CONFIGS[ci] and (r['phase']==0)==initial)
                windows.append(dict(id=f'w{len(windows)}',sample_id=r['sample_id'],transaction_id=r['transaction_id'],
                    phase=r['phase'],instr_new=r['instr_new'],instruction_hex=f"0x{r['instruction']:08x}",
                    configuration=r['configuration'],before_illegal=r['actual']['before'],after_illegal=r['actual']['after']))
    assert len(windows)==12
    dump(out/'windows.public.json',windows)
    dump(out/'expected.private.json',dict(op_illegal_bit=28,windows=[truth(w) for w in windows]))
    sources=[R51/'v1/search'/n for n in ('result.json','samples.json','before/execute.log','after/execute.log')]
    sources += [R51/'v1'/c/'result.json' for c in ('history','search')]+[R51/'v1/model_call/candidate.json',R51/'v2/model_call/model_edit.json']
    dump(out/'native_binding.json',dict(files={p.relative_to(ROOT).as_posix():old.digest(p) for p in sources}))
    source_check(out)
    current=read(out/'shared_initial.json')
    if reuse is None:
        h=old.replay(current,read(out/'history_cases.json'),'history',out/'baseline/history',out)
        s=old.replay(current,read(out/'search_cases.json'),'search',out/'baseline/search',out)
    else:
        assert ROOT in reuse.parents
        for n,sha in read(reuse/'sealed.json').items():assert old.digest(reuse/n)==sha
        assert read(reuse/'shared_initial.json')==current
        assert read(reuse/'source_hashes.json')['research51_history_loop.py']==old.digest(ROOT/'scripts/research51_history_loop.py')
        h=read(reuse/'baseline/history/result.json');s=read(reuse/'baseline/search/result.json')
        for cohort,r in [('history',h),('search',s)]:dump(out/f'baseline/{cohort}/result.json',r)
        dump(out/'baseline_reuse.json',dict(source= str(reuse.relative_to(ROOT)),
            sealed_sha256=old.digest(reuse/'sealed.json'),new_native_calls=0,
            note='Actual complete replay reused by hash; raw logs, waveforms and costs stay at source. No duplicate cost counted.'))
    for c,r in [('history',h),('search',s)]:
        archived=read(R51/f'v1/{c}/result.json')
        assert r==archived,'baseline_changed:'+c
    baseline=combine(h,s);dump(out/'baseline_full.json',baseline)
    assert baseline['counts']['misses']==420 and baseline['counts']['detections']==270
    dump(out/'qualification.json',qualify(out))
    dump(out/'plan_request.preview.json',plan_payload(out))
    dump(out/'protocol.json',dict(scope='research52_ibex_bitfield_then_sva',max_calls=4,plan_max_calls=2,sva_max_calls=2,
        endpoint=old.DEFAULT_URL,model=old.DEFAULT_MODEL,retries=0,early_stop=True,
        plan_rule='All12 samples and obligation bit independently correct before any SVA call.',
        duplicate_rule='Reject exact predicates after whitespace/enclosing-parenthesis normalization; not a general equivalence solver.',
        acceptance='All420 OP violations detected,270 prior BRANCH detections retained, legal false alarms0, critical unknown0 and required native triggers present on identical151 development transactions.',
        baseline_is_accepted=False,holdout='Not part of this run. Only accepted candidate is saved; independent acceptance is a separate subsequent task.',
        exclusions=['private answer table','handwritten control SVA','independent tests','archived successful FIFO assertions'],
        plan_request_sha256=old.digest(out/'plan_request.preview.json')))
    snap=out/'source_snapshot';snap.mkdir()
    for p in [Path(__file__),*[ROOT/'scripts'/n for n in read(P51/'source_hashes.json')]]:shutil.copy2(p,snap/p.name)
    dump(out/'source_hashes.json',{p.name:old.digest(p) for p in snap.iterdir()})
    dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():old.digest(p) for p in out.rglob('*') if p.is_file() and p.suffix in ('.json','.sv','.py')})
    print('BIT_GATE_PREPARED',len(read(out/'qualification.json')['checks']),baseline['counts'],flush=True)


def run(prep,out,auth_path):
    auth=read(auth_path);protocol=read(prep/'protocol.json')
    assert auth['scope']==protocol['scope'] and auth['authorized_calls']==4
    assert auth['endpoint']==protocol['endpoint'] and auth['plan_request_sha256']==protocol['plan_request_sha256']
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    for n,h in read(prep/'sealed.json').items():assert old.digest(prep/n)==h,n
    for n,h in read(prep/'source_hashes.json').items():assert old.digest(ROOT/'scripts'/n)==h,n
    source_check(prep)
    out.mkdir(parents=True,exist_ok=False);shutil.copy2(auth_path,out/'authorization.json')
    shutil.copytree(prep/'source_snapshot',out/'source_snapshot');dump(out/'protocol.json',protocol)
    llm=Model(out,prep);decisions=[];accepted=None;status='plan_not_accepted';feedback=None
    current=read(prep/'shared_initial.json');baseline=read(prep/'baseline_full.json')
    try:
        for i in range(2):
            folder=out/f'plan/v{i}/model_call'
            call,plan=llm.call(folder,None,'bitfield_applicability',feedback,'plan')
            verdict=validate(plan,source_check(prep));dump(folder.parent/'decision.json',verdict)
            decisions.append(dict(stage='plan',version=i,accepted=verdict['accepted']))
            if verdict['accepted']:
                llm.plan=plan;llm.verdict=verdict;dump(out/'accepted_plan.json',plan);dump(out/'accepted_plan_gate.json',verdict);break
            feedback=dict(actual_rejected_output=plan,diagnosis=verdict,call=call)
        if llm.plan is None:return
        llm.stage='sva';llm.output_kind='sva';status='no_accepted_sva'
        feedback=dict(history=old.evidence(read(prep/'baseline/history/result.json')),search=old.evidence(read(prep/'baseline/search/result.json')),
            baseline_status='Unaccepted research51 candidate. OP lacks triggers; BRANCH protection must be retained.')
        for i in range(2):
            folder=out/f'sva/v{i}'
            call,candidate=llm.call(folder/'model_call',current,'historical_repair_obligations',feedback,'sva_refinement')
            if candidate is None:
                duplicate=read(folder/'model_call/duplicate_gate.json') if (folder/'model_call/duplicate_gate.json').exists() else None
                decision=dict(accepted=False,reasons=[dict(kind='unusable_or_duplicate_proposal',details=duplicate)])
                feedback=dict(previous_actual_native_feedback=feedback,call=call,rejection=decision)
            else:
                h=old.replay(candidate,read(prep/'history_cases.json'),'history',folder/'history',prep)
                s=old.replay(candidate,read(prep/'search_cases.json'),'search',folder/'search',prep)
                full=combine(h,s);decision=old.decide(baseline,full)
                dump(folder/'obligation_mapping.json',dict(history=h['mapping'],search=s['mapping']))
                feedback=dict(actual_proposed_assertions=candidate,history=old.evidence(h),search=old.evidence(s),decision=gate_feedback(decision))
                if decision['accepted']:
                    accepted=candidate;status='accepted_development_only';dump(out/'accepted_candidate.json',candidate)
                    dump(out/'acceptance.json',dict(candidate_sha256=old.acceptance.sha(candidate),history=h['counts'],search=s['counts'],decision=decision))
            dump(folder/'decision.json',decision);decisions.append(dict(stage='sva',version=i,accepted=decision['accepted']))
            print('BIT_GATE_SVA',i,decision['accepted'],flush=True)
            if accepted is not None:break
    finally:
        dump(out/'outcome.json',dict(status=status,calls=len(llm.calls),decisions=decisions,
            accepted_candidate_sha256=old.acceptance.sha(accepted) if accepted else None,independent_test='not_run',formal_calls=0))
        dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    p.add_argument('--reuse-baseline',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve(),a.reuse_baseline.resolve() if a.reuse_baseline else None)
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
