"""Refine measured legal false alarms while retaining all exposed target detection.

Reuse native gates and real transport. Compact feedback is a view of immutable
development records, never a corrected assertion or a substitute native result.
"""
import argparse
import copy
import json
import re
import shutil
from pathlib import Path
from unittest.mock import patch
import research56_fresh_op as previous

ROOT,old,common=previous.ROOT,previous.old,previous.common
read,dump=previous.read,previous.dump
native_flow=previous.previous
P56=ROOT/'deliverables/research56_prepare_20261023_r01'
R56=ROOT/'deliverables/research56_real_20261023_r01'
MAX_MESSAGE_BYTES=79498  # Observed successful request size, NOT a token/context limit.


def row_view(row):
    s=row['sample'];word=s['instruction']
    return dict(evidence_id=row['evidence_id'],sample=s,configuration=row['configuration'],revision=row['revision'],
        instruction_hex=f'0x{word:08x}',decoded=dict(opcode=word&127,funct3=(word>>12)&7,funct7=(word>>25)&127,
        bit28=(word>>28)&1,bit31=(word>>31)&1),expected=row['expected'],observed=row['observed'],oracle=row['oracle'],
        assertions=row['native']['assertions'])


def bounded(value,key=''):
    """Preserve scalar counts; replace long diagnostic lists with explicit counts."""
    if isinstance(value,dict):return {k:bounded(v,k) for k,v in value.items()}
    if isinstance(value,list):
        if value and all(isinstance(v,str) and re.fullmatch(r'[0-9a-f]{64}',v) for v in value):
            return dict(total_items=len(value),identifiers_omitted=True)
        if len(value)>4:
            return dict(total_items=len(value),representatives=[bounded(v) for v in value[:2]],omitted_items=len(value)-2)
        return [bounded(v) for v in value]
    return value


def compact_feedback(feedback):
    # Do not recursively accumulate old prompts/attempts; the fixed development
    # evidence pack remains in every request. Only the latest diagnosis changes.
    result={k:bounded(v,k) for k,v in feedback.items() if k not in ('previous_feedback','previous_full_development_feedback','native_development_feedback')}
    result['view_scope']='Bounded latest development feedback; complete evidence and all counts retained locally. Never acceptance based on this summary.'
    return result


def payload(prep,current,feedback):
    latest=read(prep/'refinement_candidate.json')
    req=old.payload(prep,latest,compact_feedback(feedback),'legal_false_positive_refinement')
    body=json.loads(req['messages'][1]['content']);body.pop('output')
    cert=native_flow.prior.components(prep)
    body['actual_model_op_rule']=cert['actual_op_rule']
    body['measured_repair_constraints']=read(prep/'evidence_pack.json')
    body['response_contract']=dict(top_level_keys=['operation','reason','assertions'],operation='replace_op',
        assertion_keys=['antecedent','consequent','timing','obligations'],timing_values=['same_sample','next_sample'],
        obligations=['op_bit28_illegal'],assertions_count='1..3',allowed_identifiers=sorted(native_flow.ALLOWED))
    body['limits']='Return JSON with exactly operation,reason,assertions and no wrapper. operation=replace_op. Only OP properties; BRANCH a0 is immutable. Select every predicate and timing yourself. Do not report legal instructions as illegal. The framework never repairs your predicates. Previously measured failed sets and permutations are rejected.'
    body['acceptance_scope']='Remove measured legal false alarms while retaining all420 OP and270 BRANCH target detections. Native development alignment including the real false-alarm transactions precedes complete115 history plus36 search transactions. No assertion may pass by dropping required triggers. Full gate rejects false alarms or critical unknown.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'));req['seed']=5701
    return req


class Model(previous.Model):
    def __init__(self,out,prep):
        super().__init__(out,prep);self.config['options']['seed']=5701
    def _payload(self,current,target,feedback,phase):
        req=payload(self.prep,current,feedback)
        size=sum(len(m['content'].encode()) for m in req['messages'])
        if size>MAX_MESSAGE_BYTES:raise RuntimeError('local_request_byte_budget_exceeded_before_submission')
        return req


def prepare(out,resume=False,reuse=None):
    if resume:assert out.exists() and not (out/'sealed.json').exists(),'only_unsealed_preparation_can_resume'
    out.mkdir(parents=True,exist_ok=resume)
    for n,h in read(P56/'sealed.json').items():assert old.digest(P56/n)==h,n
    for n,h in read(P56/'source_hashes.json').items():assert old.digest(ROOT/'scripts'/n)==h,n
    for rev in ('before','after'):
        if resume:
            for p in (P56/rev).glob('*.sv'):assert old.digest(p)==old.digest(out/rev/p.name)
        else:shutil.copytree(P56/rev,out/rev)
    for name in ('windows.public.json','decoded.public.json','expected.private.json','native_binding.json','shared_initial.json',
                 'source_binding.json','history_cases.json','search_cases.json','development_manifest.json','baseline_full.json',
                 'protected_branch.json','component_binding.json','component_certificate.json'):
        shutil.copy2(P56/name,out/name)
    for cohort in ('history','search'):dump(out/f'baseline/{cohort}/result.json',read(P56/f'baseline/{cohort}/result.json'))
    native_flow.prior.components(out)
    candidate=read(R56/'v0/model_call/candidate.json');dump(out/'refinement_candidate.json',candidate)
    assert candidate['assertions'][0]==read(out/'protected_branch.json')
    failures=read(P56/'failure_binding.json');known=read(P56/'known_rejected_sets.json')
    known.append(dict(source='deliverables/research56_real_20261023_r01/v0/model_call/candidate.json',signature=previous.op_signature(candidate)))
    dump(out/'known_rejected_sets.json',known)
    results={c:read(R56/f'v0/{c}/result.json') for c in ('history','search')}
    selected={};targets={};counts={};detected={}
    for cohort,result in results.items():
        info=old.acceptance.inspect(result['ledger']);counts[cohort]=result['counts']
        for ob in ('op_bit28_illegal','illegal_branch_persists'):
            detected.setdefault(ob,[]);detected[ob]+=[k for k in info['detections'] if info['rows'][k]['obligation']==ob]
        for row in result['ledger']:
            if row['revision']=='after' and row['expected']==0 and row['observed']==0:
                for a in row['native']['assertions']:
                    if a['failed'] and a['id']!='a0':selected.setdefault(a['id'],dict(cohort=cohort,row=row))
            if row['evidence_id'] in info['detections']:
                key=(row['obligation'],row['sample']['phase']==0)
                targets.setdefault(key,dict(cohort=cohort,row=row))
    assert set(selected)=={'a1','a2','a3'}
    assert len(detected['op_bit28_illegal'])==420 and len(detected['illegal_branch_persists'])==270
    dump(out/'target_preservation.private.json',detected)
    pack=dict(counts=counts,target_detection_to_preserve={k:len(v) for k,v in detected.items()},
        false_alarm_total=310,representative_false_alarms=[dict(cohort=v['cohort'],**row_view(v['row'])) for v in selected.values()],
        representative_targets=[dict(cohort=v['cohort'],**row_view(v['row'])) for v in targets.values()],
        scope='Real model research56/v0, original RTL development data only. All required690 detections and zero false alarms checked on full151 transactions.')
    dump(out/'evidence_pack.json',pack)
    txns=read(P56/'alignment_cases.json');bindings=[]
    for index,(aid,item) in enumerate(selected.items()):
        source_tx=next(t for t in read(out/(item['cohort']+'_cases.json')) if t['id']==item['row']['sample']['transaction_id'])
        new=copy.deepcopy(source_tx);new['id']=1000+index;txns.append(new)
        bindings.append(dict(assertion=aid,cohort=item['cohort'],source_transaction_id=source_tx['id'],
            replay_transaction_id=new['id'],instruction=source_tx['instruction'],evidence_id=item['row']['evidence_id']))
    dump(out/'alignment_cases.json',txns);dump(out/'added_legal_probe_binding.json',bindings)
    for path in [R56/'v0/model_call/candidate.json',R56/'v0/model_call/model_edit.json',R56/'v0/model_call/response.stream.raw',
                 R56/'v0/decision.json',R56/'v1/model_call/request.json',R56/'v1/model_call/result.json',
                 *[R56/f'v0/{c}/result.json' for c in ('history','search')]]:
        failures[path.relative_to(ROOT).as_posix()]=old.digest(path)
    dump(out/'failure_binding.json',failures)
    feedback=dict(task='Refine the actual current model OP set to remove its measured false alarms. Retain all target detection.',
        last_decision=bounded(read(R56/'v0/decision.json')))
    dump(out/'initial_feedback.json',feedback)
    qualification_sources={}
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    check('actual_overbroad_proposal_repeated_rejected',not previous.novelty(candidate,known)['accepted'])
    check('all_151_words_unchanged',read(out/'development_manifest.json')==read(P56/'development_manifest.json'))
    check('probes_are_development',all(t['instruction'] in read(out/'development_manifest.json')['all_used_instructions'] for t in txns))
    check('no_duplicate_replay_ids',len({t['id'] for t in txns})==len(txns))
    for label,control,want in [('actual_overbroad',candidate,False),('local_correct_control',read(previous.P55/'qualification/correct_local_control/candidate.json'),True)]:
        location=out/f'qualification/{label}'
        if resume or reuse:
            measured=(reuse/f'qualification/{label}') if reuse else location
            assert read(measured/'candidate.json')==control
            for rev in ('before','after'):
                for p in (out/rev).glob('*.sv'):assert old.digest(p)==old.digest((reuse or out)/rev/p.name)
            r=read(measured/'native/result.json');gate=read(measured/'native/alignment_gate.json')
            if reuse:
                dump(location/'candidate.json',control)
                qualification_sources[label]=(measured/'native').relative_to(ROOT).as_posix()
                for p in measured.rglob('*'):
                    if p.is_file() and ('obj_dir' not in p.parts) and p.suffix in ('.json','.log','.sv'):
                        failures[p.relative_to(ROOT).as_posix()]=old.digest(p)
        else:
            dump(location/'candidate.json',control)
            r,gate=native_flow.alignment(control,out,location/'native')
        check('native_gate/'+label,gate['accepted']==want)
        if not want:check('misclassification_reproduced',r['counts']['false_positives']>0 and r['counts']['misses']==0)
        print('LEGAL_PROBE_CONTROL',label,gate['accepted'],flush=True)
    dump(out/'qualification_sources.json',qualification_sources)
    dump(out/'failure_binding.json',failures)
    req=payload(out,read(out/'shared_initial.json'),feedback);size=sum(len(m['content'].encode()) for m in req['messages'])
    previous_req=read(R56/'v1/model_call/request.json');old_size=sum(len(m['content'].encode()) for m in previous_req['messages'])
    old_feedback=json.loads(previous_req['messages'][1]['content'])['actual_development_feedback']
    compact=compact_feedback(old_feedback)
    simulated=payload(out,read(out/'shared_initial.json'),old_feedback)
    simulated_size=sum(len(m['content'].encode()) for m in simulated['messages'])
    check('initial_within_local_byte_budget',size<=MAX_MESSAGE_BYTES)
    check('old_real_diagnosis_within_local_byte_budget',simulated_size<=MAX_MESSAGE_BYTES)
    check('old_false_alarm_count_preserved',compact['history']['counts']['false_positives']==226 and compact['search']['counts']['false_positives']==84)
    check('actual_property_set_in_prompt',json.loads(req['messages'][1]['content'])['current_assertions']==candidate)
    check('no_private_target_keys', 'target_preservation.private' not in json.dumps(req))
    check('no_model_answer_template',"instr[6:0]==7'h33 && instr[28]" not in json.dumps(req))
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=Model(out/'local_transport_metadata',out)
        check('transport_exact_request',model._payload(read(out/'shared_initial.json'),None,feedback,'sva')==req)
        check('two_calls_and_no_submission',model.config['max_model_calls']==2 and model.calls==[])
    dump(out/'request.preview.json',req)
    dump(out/'qualification.json',dict(passed=True,checks=checks,model_calls=0,local_correct_control_not_model_output=True))
    dump(out/'request_size_diagnosis.json',dict(old_failed_message_bytes=old_size,new_initial_message_bytes=size,
        old_feedback_reencoded_message_bytes=simulated_size,local_max_message_bytes=MAX_MESSAGE_BYTES,
        old_http_status=400,root_cause='Unknown; body unavailable. Byte cap and compact feedback are prospective controls, not proof of cause or server acceptance.'))
    protocol=read(P56/'protocol.json');protocol.update(scope='research57_legal_refinement',request_sha256=old.digest(out/'request.preview.json'),
        initial_context_change='Actual research56/v0 candidate plus compact real legal false alarms and required target evidence.',
        preservation='All420 OP and270 BRANCH detections must remain. Full151 requires zero false alarms and unknown.',
        request_byte_cap=MAX_MESSAGE_BYTES,added_legal_probe_transactions=3)
    dump(out/'protocol.json',protocol)
    snap=out/'source_snapshot';snap.mkdir()
    for p in [Path(__file__),*[ROOT/'scripts'/n for n in read(P56/'source_hashes.json')]]:shutil.copy2(p,snap/p.name)
    dump(out/'source_hashes.json',{p.name:old.digest(p) for p in snap.iterdir()})
    dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():old.digest(p) for p in out.rglob('*') if p.is_file() and (p.suffix in ('.json','.py','.sv','.sva') or p.name=='execute.log')})
    print('LEGAL_REFINEMENT_PREPARED',len(checks),'checks; model0',flush=True)


def run(prep,out,auth):
    with patch.object(native_flow,'Model',Model):native_flow.run(prep,out,auth)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    p.add_argument('--resume-unsealed',action='store_true')
    p.add_argument('--reuse-qualification-from',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve(),a.resume_unsealed,a.reuse_qualification_from.resolve() if a.reuse_qualification_from else None)
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
