"""Explicit native first/held-phase gate for the twelve exposed OP samples.

The 12-point subset augments, never replaces, the existing 9-transaction gate.
No changes to DUT, model predicates, ISA oracle or complete151 acceptance.
"""
import argparse
import copy
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import research58_preservation_refinement as prior

ROOT,old,read,dump=prior.ROOT,prior.old,prior.read,prior.dump
P=ROOT/'deliverables/research58_prepare_20261023_r01'
R=ROOT/'deliverables/research58_real_20261023_r01'
BASE_ALIGNMENT=prior.prior.native_flow.alignment


def focus_gate(result,manifest):
    checks=[];phase_counts={k:dict(exposed=0,detected=0,triggered_revision_points=0) for k in ('first','held')}
    for e in manifest['targets']:
        rows=[r for r in result['ledger'] if r['sample']['sample_id']==e['sample_id'] and r['configuration']==e['configuration']]
        before=[r for r in rows if r['revision']=='before'];after=[r for r in rows if r['revision']=='after']
        bound=len(before)==len(after)==1 and all(r['sample']==e['sample'] and r['obligation']=='op_bit28_illegal' and r['required'] and r['expected']==1 for r in rows)
        valid=bound and before[0]['observed']==0 and after[0]['observed']==1
        executed=bound and all(r['native']['compile']=='ok' and r['native']['execution']=='ok' and r['native']['support']=='supported' and r['native']['attribution_status']=='confirmed' for r in rows)
        triggers=sum(any(a['trigger'] for a in r['native']['assertions'] if a['id']!='a0') for r in rows) if bound else 0
        detected=bound and any(a['causal_detection'] for a in before[0]['native']['assertions'] if a['id']!='a0')
        phase='first' if e['sample']['phase']==0 else 'held'
        counts=phase_counts[phase];counts['exposed']+=int(valid);counts['detected']+=int(detected);counts['triggered_revision_points']+=triggers
        checks.append(dict(sample_id=e['sample_id'],configuration=e['configuration'],phase=phase,
            bound=bool(bound),independent_violation=bool(valid),native_execution_confirmed=bool(executed),
            triggered_revision_points=triggers,detected=bool(detected),passed=bool(valid and executed and detected and triggers==2)))
    passed=len(checks)==12 and phase_counts['first']['exposed']==3 and phase_counts['held']['exposed']==9 and all(c['passed'] for c in checks)
    return dict(accepted=passed,phases=phase_counts,checks=checks,
        scope='Twelve fixed development sample/configuration points; all9 transactions and full151 remain mandatory.')


def alignment(candidate,prep,folder):
    result,gate=BASE_ALIGNMENT(candidate,prep,folder)
    focus=focus_gate(result,read(prep/'focus.private.json'))
    gate['focus12']=focus;gate['accepted']=gate['accepted'] and focus['accepted']
    dump(folder/'focus_gate.json',focus);dump(folder/'alignment_gate.json',gate)
    return result,gate


def compact(feedback):
    # Keep current actual proposal plus small latest native evidence, not nested
    # histories or full failed-window lists. The sealed stage table stays visible.
    result={k:prior.prior.bounded(feedback[k]) for k in ('task','actual_model_proposal','actual_interface_diagnosis','decision') if k in feedback}
    for key in ('native_evidence','history','search'):
        if key in feedback:
            v=feedback[key]
            result[key]=prior.prior.bounded(v)
    if 'native_alignment_gate' in feedback:
        v=feedback['native_alignment_gate']
        result['native_alignment_gate']={k:prior.prior.bounded(v[k]) for k in ('accepted','counts','required_untriggered','native_status') if k in v}
        if 'focus12' in v:result['phase_counts']=v['focus12']['phases']
    return result


def payload(prep,current,feedback):
    req=prior.payload(prep,current,compact(feedback));body=json.loads(req['messages'][1]['content'])
    body['native_stage_table']=read(prep/'phase_table.public.json')
    body['sampling_semantics']='Original combinational decoder. instr_new=1 first sample; instr_new=0 held samples. No ready/valid handshake is invented. Both first and held samples have independently confirmed OP obligations. A property that never triggers does not protect them.'
    body['feedback_provenance']='Actual research58 failed model properties and native development execution. The focused12 gate augments all9 transactions, never replaces them.'
    body['limits']+=' Select executable conditions yourself. Restoring first-phase checks alone is insufficient. All current and prior target protections remain required.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'));req['seed']=5901
    return req


class Model(prior.Model):
    def __init__(self,out,prep):super().__init__(out,prep);self.config['options']['seed']=5901
    def _payload(self,current,target,feedback,phase):
        req=payload(self.prep,current,feedback)
        if sum(len(m['content'].encode()) for m in req['messages'])>prior.prior.MAX_MESSAGE_BYTES:
            raise RuntimeError('local_request_byte_budget_exceeded_before_submission')
        return req


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in read(P/'sealed.json').items():check('parent/'+n,old.digest(P/n)==h)
    for n,h in read(P/'source_hashes.json').items():check('parent_code/'+n,old.digest(ROOT/'scripts'/n)==h)
    names=('windows.public.json','decoded.public.json','expected.private.json','native_binding.json',
        'shared_initial.json','source_binding.json','history_cases.json','search_cases.json','development_manifest.json',
        'baseline_full.json','protected_branch.json','component_binding.json','component_certificate.json',
        'target_preservation.private.json','known_rejected_sets.json','failure_binding.json','alignment_cases.json')
    for n in names:shutil.copy2(P/n,out/n)
    for n in ('before','after','baseline'):shutil.copytree(P/n,out/n)
    prior.prior.native_flow.prior.components(out)
    result=read(R/'v0/alignment/result.json');candidate=read(R/'v0/model_call/candidate.json')
    check('source_native',prior.diagnostic.audit_native(R/'v0/alignment',candidate,P,'alignment')==240)
    info=old.acceptance.inspect(result['ledger']);targets=[];table={}
    for r in result['ledger']:
        if r['evidence_id'] not in info['misses']:continue
        s=r['sample'];check('actual12_op',r['obligation']=='op_bit28_illegal' and r['revision']=='before')
        twin=next(t for t in result['ledger'] if t['sample']==s and t['configuration']==r['configuration'] and t['revision']=='after')
        check('independent_original_violation',r['expected']==twin['expected']==1 and r['observed']==0 and twin['observed']==1)
        targets.append(dict(sample_id=s['sample_id'],sample=s,configuration=r['configuration'],source_evidence_id=r['evidence_id']))
        key=s['sample_id']
        if key not in table:
            table[key]=dict(sample=s,instruction_hex=f"0x{s['instruction']:08x}",before_illegal=r['observed'],after_illegal=twin['observed'],
                expected_illegal=r['expected'],configurations=[],native_op_triggers=r['native']['assertions'])
        table[key]['configurations'].append(r['configuration'])
    manifest=dict(targets=targets,first=3,held=9)
    check('twelve_fixed',len(targets)==12 and len(table)==4 and {t['sample']['phase'] for t in targets}=={0,1,2,3})
    dump(out/'focus.private.json',manifest);dump(out/'phase_table.public.json',list(table.values()))
    dump(out/'refinement_candidate.json',candidate)
    # Retain measured legal failures and the complementary funct3 boundary
    # samples in the public evidence pack; do not include full private ID lists.
    pack=read(P/'evidence_pack.json');dump(out/'evidence_pack.json',pack)
    known=read(out/'known_rejected_sets.json');known.append(dict(source=(R/'v0/model_call/candidate.json').relative_to(ROOT).as_posix(),signature=prior.prior.previous.op_signature(candidate)))
    dump(out/'known_rejected_sets.json',known)
    binding=read(out/'failure_binding.json')
    for p in [R/'outcome.json',R/'v0/model_call/model_edit.json',R/'v0/model_call/candidate.json',R/'v0/model_call/response.stream.raw',R/'v0/alignment/result.json',R/'v0/alignment/alignment_gate.json']:
        binding[p.relative_to(ROOT).as_posix()]=old.digest(p)
    dump(out/'failure_binding.json',binding)
    feedback=dict(task='Repair the actual12 missed OP samples, covering first and held phases, while retaining all other target detection and zero legal false alarms.',native_development_feedback=dict(counts=result['counts']))
    dump(out/'initial_feedback.json',feedback)
    good=read(prior.prior.previous.P55/'qualification/correct_local_control/candidate.json')
    first_only=read(prior.prior.previous.P55/'qualification/first_phase_only_control/candidate.json')
    for label,c,want in [('actual_model',candidate,False),('local_positive',good,True),('local_first_only',first_only,False)]:
        folder=out/'qualification'/label;dump(folder/'candidate.json',c)
        measured,gate=alignment(c,out,folder/'native')
        check('native/'+label,gate['accepted']==want)
        check('raw/'+label,prior.diagnostic.audit_native(folder/'native',c,out,'alignment')==240)
        if label=='local_first_only':
            check('first_only_3of12',gate['focus12']['phases']['first']['detected']==3 and gate['focus12']['phases']['held']['detected']==0)
        print('PHASE_GATE',label,gate['accepted'],gate['focus12']['phases'],flush=True)
    positive=read(out/'qualification/local_positive/native/result.json')
    # Checker failure-path tests are explicitly local mutations, not native runs.
    for label,modify in [('missing_row',lambda rows:rows.pop(next(i for i,r in enumerate(rows) if r['sample']['sample_id']==6))),
        ('wrong_cycle',lambda rows:next(r for r in rows if r['sample']['sample_id']==6)['sample'].update(instr_new=0)),
        ('unknown',lambda rows:next(r for r in rows if r['sample']['sample_id']==6)['native'].update(attribution_status='unknown'))]:
        mutated=copy.deepcopy(positive);modify(mutated['ledger']);check('local_mutation_reject/'+label,not focus_gate(mutated,manifest)['accepted'])
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=Model(out/'transport_metadata',out)
        req=model._payload(read(out/'shared_initial.json'),None,feedback,'sva')
        # Use the largest actual known alignment feedback, not merely a toy.
        follow=dict(actual_model_proposal=read(R/'v0/model_call/model_edit.json'),native_alignment_gate=read(out/'qualification/actual_model/native/alignment_gate.json'),native_evidence=old.evidence(result))
        retry=model._payload(read(out/'shared_initial.json'),None,follow,'sva')
        check('no_real_calls',not model.calls)
    check('control_not_sent',good['assertions'][1]['antecedent'] not in json.dumps(req))
    private=read(out/'target_preservation.private.json');allowed={r['evidence_id'] for r in pack['representatives']}
    check('private_ids_not_sent',all(k not in json.dumps(req) or k in allowed for ids in private.values() for k in ids))
    dump(out/'request.preview.json',req)
    dump(out/'request_sizes.json',dict(first=sum(len(m['content'].encode()) for m in req['messages']),actual_failure_feedback=sum(len(m['content'].encode()) for m in retry['messages']),max=prior.prior.MAX_MESSAGE_BYTES))
    protocol=read(P/'protocol.json');protocol.update(scope='research59_first_held_native_gate',seed=5901,request_sha256=old.digest(out/'request.preview.json'),focus_target_points=12,
        focus_first_points=3,focus_held_points=9,initial_context_change='Actual research58 model and first/held native table; all9 and full151 retained.')
    dump(out/'protocol.json',protocol)
    snap=out/'source_snapshot';snap.mkdir()
    for n in {Path(__file__).name,*read(P/'source_hashes.json')}:shutil.copy2(ROOT/'scripts'/n,snap/n)
    dump(out/'source_hashes.json',{p.name:old.digest(p) for p in snap.iterdir()})
    dump(out/'qualification.json',dict(passed=True,checks=checks,model_calls=0,local_controls_not_model_results=True))
    dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():old.digest(p) for p in out.rglob('*') if p.is_file() and 'obj_dir' not in p.parts and p.suffix in ('.json','.py','.sv','.sva','.log')})
    print('PHASE_PREPARED',len(checks),'checks',flush=True)


def run(prep,out,auth):
    decide=old.decide
    with patch.object(prior.prior.native_flow,'Model',Model),patch.object(prior.prior.native_flow,'alignment',alignment),patch.object(old,'decide',lambda b,c:prior.preserve(b,c,read(prep/'target_preservation.private.json'),decide)):
        prior.prior.native_flow.run(prep,out,auth)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
