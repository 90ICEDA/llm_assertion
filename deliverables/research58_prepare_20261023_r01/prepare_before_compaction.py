"""Evidence-bound refinement of actual false alarms AND lost OP protection.

No new predicates are constructed here. Optional IDs are metadata only. Native
controls are local fixtures; all generated properties must come from real calls.
"""
import argparse
import copy
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import research57_legal_refinement as prior
import research57_label_replay as diagnostic

ROOT, old, read, dump = prior.ROOT, prior.old, prior.read, prior.dump
P = ROOT/'deliverables/research57_prepare_20261023_r02'
R = ROOT/'deliverables/research57_real_20261023_r01'
D = ROOT/'deliverables/research57_label_replay_20261023_r01'


def payload(prep,current,feedback):
    req=prior.payload(prep,current,feedback)
    body=json.loads(req['messages'][1]['content'])
    body['response_contract']['optional_assertion_keys']=['id']
    body['response_contract']['id_rule']='Optional unique label, identifier syntax, reserved a0 forbidden. Labels do not affect predicates.'
    body['limits'] += ' Optional assertion id labels are accepted as metadata. Repair both lost target protection and legal false alarms using the measured paired samples. Do not exclude a required instruction family merely to reduce false alarms.'
    body['feedback_provenance']='Both prior real responses were separately replayed unchanged after optional-label adaptation. These semantic diagnoses were not in research57 second-call feedback. All presented samples are development data.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'));req['seed']=5801
    return req


class Model(prior.Model):
    def __init__(self,out,prep):
        super().__init__(out,prep);self.config['options']['seed']=5801
    def _payload(self,current,target,feedback,phase):
        req=payload(self.prep,current,feedback)
        if sum(len(m['content'].encode()) for m in req['messages'])>prior.MAX_MESSAGE_BYTES:
            raise RuntimeError('local_request_byte_budget_exceeded_before_submission')
        return req
    def save_decoded_output(self,folder,value,current,secret):
        try:
            candidate,labels=diagnostic.adapt(value,current)
        except (ValueError,TypeError,KeyError,AssertionError) as exc:
            dump(folder/'interface_gate.json',dict(accepted=False,errors=[dict(kind='label_compatible_interface',detail=str(exc))]))
            return None,'interface_rejected'
        clean=copy.deepcopy(value)
        for a in clean['assertions']:a.pop('id',None)
        dump(folder/'label_mapping.json',dict(labels=labels,predicates_rewritten=False))
        accepted,status=super().save_decoded_output(folder,clean,current,secret)
        assert read(folder/'candidate.json')==candidate
        return accepted,status


def preserve(base,combined,protected,decide):
    decision=decide(base,combined)
    info=old.acceptance.inspect(combined['ledger'])
    lost={ob:sorted(set(ids)-info['detections']) for ob,ids in protected.items()}
    decision['target_preservation']={ob:dict(required=len(ids),lost=len(lost[ob])) for ob,ids in protected.items()}
    if any(lost.values()):
        decision['accepted']=False
        decision['reasons'].append(dict(kind='lost_required_target_detections',evidence=lost))
    return decision


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        assert ok,name
    for n,h in read(P/'sealed.json').items():check('parent_seal/'+n,old.digest(P/n)==h)
    for n,h in read(P/'source_hashes.json').items():check('parent_code/'+n,old.digest(ROOT/'scripts'/n)==h)
    # Copy only reusable inputs; never copy old qualification or its acceptance.
    names=('windows.public.json','decoded.public.json','expected.private.json','native_binding.json',
        'shared_initial.json','source_binding.json','history_cases.json','search_cases.json','development_manifest.json',
        'baseline_full.json','protected_branch.json','component_binding.json','component_certificate.json',
        'target_preservation.private.json','known_rejected_sets.json','failure_binding.json')
    for n in names:shutil.copy2(P/n,out/n)
    for n in ('before','after','baseline'):shutil.copytree(P/n,out/n)
    prior.native_flow.prior.components(out)
    protected=read(out/'target_preservation.private.json');known=read(out/'known_rejected_sets.json')
    binding=read(out/'failure_binding.json');representatives=[];lost_transactions={};summaries={}
    for v in ('v0','v1'):
        candidate=read(D/v/'candidate.json')
        raw=read(R/v/'model_call/model_edit.json')
        check(v+'/exact_response_adapter',diagnostic.adapt(raw,read(out/'shared_initial.json'))[0]==candidate)
        known.append(dict(source=(D/v/'candidate.json').relative_to(ROOT).as_posix(),signature=prior.previous.op_signature(candidate)))
        for cohort in ('history','search'):
            result=read(D/v/cohort/'result.json')
            check(v+'/'+cohort+'/raw_native_audit',diagnostic.audit_native(D/v/cohort,candidate,P,cohort)==len(result['ledger']))
            summaries[v+'/'+cohort]=result['counts'];info=old.acceptance.inspect(result['ledger'])
            selected={}
            for row in result['ledger']:
                s=row['sample'];f3=(s['instruction']>>12)&7
                if row['evidence_id'] in set(protected['op_bit28_illegal'])-info['detections']:
                    key=('lost_target',f3,s['phase']==0)
                    selected.setdefault(key,row)
                    if cohort=='history':lost_transactions.setdefault(f3,(cohort,s['transaction_id']))
                elif row['revision']=='after' and row['expected']==row['observed']==0 and any(a['failed'] for a in row['native']['assertions']):
                    selected.setdefault(('legal_false_alarm',f3),row)
            # Deterministic representatives, paired with actual fixed/buggy outputs.
            if cohort=='history':
                for key,row in selected.items():
                    twin=next(r for r in result['ledger'] if r['sample']==row['sample'] and r['configuration']==row['configuration'] and r['revision']!=row['revision'])
                    representatives.append(dict(version=v,kind=key[0],cohort=cohort,**prior.row_view(row),
                        paired_actual={row['revision']:row['observed'],twin['revision']:twin['observed']}))
        for p in (D/v).rglob('*'):
            if p.is_file() and 'obj_dir' not in p.parts and p.suffix in ('.json','.sv','.sva','.log'):
                binding[p.relative_to(ROOT).as_posix()]=old.digest(p)
        for n in ('model_edit.json','response.stream.raw','response.assembled.json'):
            p=R/v/'model_call'/n;binding[p.relative_to(ROOT).as_posix()]=old.digest(p)
    dump(out/'known_rejected_sets.json',known);dump(out/'failure_binding.json',binding)
    dump(out/'refinement_candidate.json',read(D/'v0/candidate.json'))
    pack=dict(actual_counts=summaries,representatives=representatives,
        required_target_counts={k:len(v) for k,v in protected.items()},
        scope='Actual unchanged research57 predicates, independently checked original RTL observations. All are development samples; full target ID lists remain private.')
    dump(out/'evidence_pack.json',pack)
    txns=read(P/'alignment_cases.json');bindings=[]
    for f3,(cohort,tid) in sorted(lost_transactions.items()):
        source=next(t for t in read(out/(cohort+'_cases.json')) if t['id']==tid)
        new={**source,'id':2000+f3};txns.append(new)
        bindings.append(dict(funct3=f3,cohort=cohort,original_id=tid,replay_id=new['id'],instruction=source['instruction']))
    check('lost_funct3_2_and3',set(lost_transactions)=={2,3})
    check('no_replay_id_collision',len(txns)==len({t['id'] for t in txns}))
    check('all_probes_development',all(t['instruction'] in read(out/'development_manifest.json')['all_used_instructions'] for t in txns))
    dump(out/'alignment_cases.json',txns);dump(out/'lost_probe_binding.json',bindings)
    feedback=dict(task='Eliminate legal false alarms while restoring every lost OP detection. Preserve immutable BRANCH.',
        native_development_feedback=dict(measured_counts=summaries,previous_versions_rejected=True))
    dump(out/'initial_feedback.json',feedback)
    current=read(out/'shared_initial.json');good=read(prior.previous.P55/'qualification/correct_local_control/candidate.json')
    for label,candidate,want in [('actual_v0',read(D/'v0/candidate.json'),False),('actual_v1',read(D/'v1/candidate.json'),False),('local_control',good,True)]:
        folder=out/'qualification'/label;dump(folder/'candidate.json',candidate)
        result,gate=prior.native_flow.alignment(candidate,out,folder/'native')
        check('native/'+label,gate['accepted']==want)
        if not want:check('both_failure_modes/'+label,result['counts']['misses']>0 and result['counts']['false_positives']>0)
        print('PRESERVATION_CONTROL',label,gate['accepted'],result['counts'],flush=True)
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=Model(out/'local_transport',out)
        for v in ('v0','v1'):
            folder=out/'local_transport'/v;folder.mkdir(parents=True)
            result,status=model.save_decoded_output(folder,read(R/v/'model_call/model_edit.json'),current,'local_fixture')
            check('repeat_rejected/'+v,result is None and status=='previously_measured_or_duplicate_op_rejected')
            check('exact_predicates/'+v,read(folder/'candidate.json')==read(D/v/'candidate.json'))
        req=model._payload(current,None,feedback,'sva');check('no_calls',not model.calls)
    # Isolate the additional preservation guard from the ordinary acceptance gate.
    combined=prior.common.combine(read(D/'v0/history/result.json'),read(D/'v0/search/result.json'))
    fake_accept=lambda *_:dict(accepted=True,reasons=[])
    decision=preserve(read(out/'baseline_full.json'),combined,protected,fake_accept)
    check('preservation_guard_rejects_even_if_other_gate_passes',not decision['accepted'] and decision['target_preservation']['op_bit28_illegal']['lost']==102)
    text=json.dumps(req);allowed={r['evidence_id'] for r in representatives}
    check('no_private_target_ids',all(k not in text or k in allowed for ids in protected.values() for k in ids))
    check('no_control_property',good['assertions'][1]['antecedent'] not in text)
    check('no_independent_test',not any(k in text for k in ('independent_cases.json','holdout_cases.json')))
    check('old_failures_unchanged',read(R/'outcome.json')['status']=='no_accepted_sva' and not read(D/'outcome.json')['frozen'])
    dump(out/'request.preview.json',req)
    protocol=read(P/'protocol.json');protocol.update(scope='research58_preservation_refinement',
        request_sha256=old.digest(out/'request.preview.json'),seed=5801,
        initial_context_change='Actual research57 v0, paired legal false alarms and lost-target observations from v0 and v1.',
        added_lost_probe_transactions=len(bindings),optional_ids='validated metadata only',
        stage_order=['label_compatible_interface','order_independent_novelty','expanded_native_alignment','full151_native_acceptance','explicit690_detection_preservation'])
    dump(out/'protocol.json',protocol)
    snap=out/'source_snapshot';snap.mkdir()
    files={Path(__file__).name,Path(diagnostic.__file__).name,*read(P/'source_hashes.json')}
    for n in files:shutil.copy2(ROOT/'scripts'/n,snap/n)
    dump(out/'source_hashes.json',{p.name:old.digest(p) for p in snap.iterdir()})
    dump(out/'qualification.json',dict(passed=True,checks=checks,model_calls=0,request_bytes=sum(len(m['content'].encode()) for m in req['messages'])))
    dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():old.digest(p) for p in out.rglob('*') if p.is_file() and 'obj_dir' not in p.parts and p.suffix in ('.py','.json','.sv','.sva','.log')})
    print('PRESERVATION_PREPARED',len(checks),'checks; model0',flush=True)


def run(prep,out,auth):
    decide=old.decide;protected=read(prep/'target_preservation.private.json')
    with patch.object(prior.native_flow,'Model',Model),patch.object(old,'decide',lambda b,c:preserve(b,c,protected,decide)):
        prior.native_flow.run(prep,out,auth)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
