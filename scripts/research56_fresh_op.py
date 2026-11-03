"""Fresh OP synthesis with order-independent rejection of measured old proposals.

Reuse research55's real transport and native gates. Preserve its sealed source
and failures. Never edit model predicates or manufacture OP from the plan.
"""
import argparse
import copy
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import research55_native_plan_alignment as previous

ROOT, old, common = previous.ROOT, previous.old, previous.common
read, dump = previous.read, previous.dump
P55=ROOT/'deliverables/research55_prepare_20261023_r01'
R55=ROOT/'deliverables/research55_real_20261023_r01'


def op_signature(candidate):
    return tuple(sorted({common.signature(a) for a in candidate['assertions'] if 'op_bit28_illegal' in a['obligations']}))


def novelty(candidate, known):
    signature=op_signature(candidate)
    matches=[r['source'] for r in known if signature==tuple(tuple(s) for s in r['signature'])]
    within=common.duplicates(candidate,None,'replace')
    reasons=[]
    if matches:reasons.append(dict(kind='previously_rejected_op_set',sources=matches))
    if not within['accepted']:reasons.extend(within['reasons'])
    return dict(accepted=not reasons,reasons=reasons,signature=signature,
        scope='Order, IDs, reason text, whitespace and enclosing parentheses ignored. Not general logical equivalence or semantic acceptance.')


def payload(prep,current,feedback):
    req=previous.payload(prep,current,feedback)
    body=json.loads(req['messages'][1]['content'])
    body['current_assertions']={'assertions':[copy.deepcopy(current['assertions'][0])]}
    body['generation_scope']=(
        'Synthesize OP properties anew from the verified model OP judgment, original RTL and native development evidence. '
        'Only the immutable BRANCH property is shown as current_assertions. The failed OP predicates are intentionally '
        'not provided as editable templates in the initial request. The full failed baseline is still retained locally '
        'for all acceptance comparisons; it is not silently replaced. Select every OP operand and timing yourself. '
        'No plan is automatically translated into a property. Merely reordering a measured failed set is rejected before compilation.')
    req['messages'][1]['content']=json.dumps(body);req['seed']=5601
    return req


class Model(previous.Model):
    def __init__(self,out,prep):
        super().__init__(out,prep)
        self.config['options']['seed']=5601
        self.known=read(prep/'known_rejected_sets.json')
    def _payload(self,current,target,feedback,phase):return payload(self.prep,current,feedback)
    def save_decoded_output(self,folder,value,current,secret):
        candidate,interface=previous.frontend(value,current)
        if candidate is None:
            dump(folder/'interface_gate.json',interface)
            return None,'interface_rejected_with_structured_diagnostics'
        assert candidate['assertions'][0]==read(self.prep/'protected_branch.json')
        dump(folder/'candidate.json',candidate)
        (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n')
        verdict=novelty(candidate,self.known);dump(folder/'novelty_gate.json',verdict)
        if not verdict['accepted']:
            dump(folder/'interface_gate.json',dict(accepted=False,errors=verdict['reasons'],
                syntactic_interface=interface,stage='order_independent_novelty',native_execution='skipped'))
            return None,'previously_measured_or_duplicate_op_rejected'
        self.known.append(dict(source=str(folder/'candidate.json'),signature=op_signature(candidate)))
        dump(folder/'interface_gate.json',interface)
        return candidate,'exact_new_model_op_native_acceptance_pending'


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    for n,h in read(P55/'sealed.json').items():assert old.digest(P55/n)==h,n
    for n,h in read(P55/'source_hashes.json').items():assert old.digest(ROOT/'scripts'/n)==h,n
    for rev in ('before','after'):shutil.copytree(P55/rev,out/rev)
    for name in ('windows.public.json','decoded.public.json','expected.private.json','native_binding.json',
                 'shared_initial.json','source_binding.json','history_cases.json','search_cases.json','development_manifest.json',
                 'baseline_full.json','protected_branch.json','component_binding.json','component_certificate.json','alignment_cases.json'):
        shutil.copy2(P55/name,out/name)
    for cohort in ('history','search'):dump(out/f'baseline/{cohort}/result.json',read(P55/f'baseline/{cohort}/result.json'))
    previous.prior.components(out)
    current=read(out/'shared_initial.json');known=[];binding=read(P55/'failure_binding.json')
    for p in [common.R51/'v1/model_call/candidate.json',R55/'v0/model_call/candidate.json',R55/'v1/model_call/candidate.json']:
        binding[p.relative_to(ROOT).as_posix()]=old.digest(p)
        known.append(dict(source=p.relative_to(ROOT).as_posix(),signature=op_signature(read(p))))
    for v in ('v0','v1'):
        for name in ('decision.json','alignment/result.json','alignment/alignment_gate.json','model_call/model_edit.json','model_call/response.stream.raw'):
            p=R55/v/name;binding[p.relative_to(ROOT).as_posix()]=old.digest(p)
    for p in (P55/'qualification.json',ROOT/'deliverables/research55_preflight_20261023_r01/result.json'):
        binding[p.relative_to(ROOT).as_posix()]=old.digest(p)
    dump(out/'known_rejected_sets.json',known);dump(out/'failure_binding.json',binding)
    feedback=dict(native_development_feedback=read(P55/'initial_feedback.json')['native_development_feedback'],
        measured_latest_gate=read(R55/'v0/alignment/alignment_gate.json'),
        measured_latest_evidence=old.evidence(read(R55/'v0/alignment/result.json')),
        prior_failure='The previous OP sets failed every required OP trigger and missed12 exposed violations on the small native development gate. Their prose and permutations did not repair the executable behavior.')
    dump(out/'initial_feedback.json',feedback)
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    first=read(R55/'v0/model_call/candidate.json');second=read(R55/'v1/model_call/candidate.json')
    check('actual_reordered_proposals_match',op_signature(first)==op_signature(second))
    for name,candidate in [('baseline',current),('actual_v0',first),('actual_v1',second)]:
        check('known_failed_set_rejected/'+name,not novelty(candidate,known)['accepted'])
    for label,edit in [('reverse',lambda c:c['assertions'].reverse()),('ids',lambda c:[a.update(id=f'other{i}') for i,a in enumerate(c['assertions'])]),
                       ('whitespace',lambda c:[a.update(antecedent=' ( '+a['antecedent']+' ) ') for a in c['assertions']])]:
        c=copy.deepcopy(first);edit(c);check('rejection_ignores/'+label,not novelty(c,known)['accepted'])
    # Existing measured controls are local fixtures only, never model outputs.
    local_good=read(P55/'qualification/correct_local_control/candidate.json')
    local_weak=read(P55/'qualification/vacuous_consequent_control/candidate.json')
    check('novelty_not_literal_ban_correct_control',novelty(local_good,known)['accepted'])
    check('novelty_not_semantic_gate_weak_control',novelty(local_weak,known)['accepted'])
    check('native_gate_still_rejects_weak_control',not read(P55/'qualification/vacuous_consequent_control/native/alignment_gate.json')['accepted'])
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=Model(out/'local_interface_checks/transport_metadata_only',out)
        req=model._payload(current,None,feedback,'sva')
        check('two_call_budget',model.config['max_model_calls']==2)
        for version in ('v0','v1'):
            folder=out/'local_interface_checks'/version;folder.mkdir(parents=True)
            raw=read(R55/version/'model_call/model_edit.json')
            candidate,status=model.save_decoded_output(folder,raw,current,'local_fixture_no_credential')
            check('actual_transport_decode_path_rejects/'+version,candidate is None and status=='previously_measured_or_duplicate_op_rejected')
            check('no_predicate_rewrite/'+version,read(folder/'candidate.json')==read(R55/version/'model_call/candidate.json'))
        check('no_model_calls',model.calls==[])
    body=json.loads(req['messages'][1]['content'])
    check('only_immutable_branch_as_current',body['current_assertions']==dict(assertions=[current['assertions'][0]]))
    check('verified_plan_unchanged',body['actual_model_op_rule']==read(out/'component_certificate.json')['actual_op_rule'])
    check('failed_OP_not_template',all(a['property'] not in json.dumps(req) and a['antecedent'] not in json.dumps(req) for a in first['assertions'] if a['id']!='a0'))
    check('no_local_correct_OP_template',local_good['assertions'][1]['antecedent'] not in json.dumps(req))
    check('baseline_acceptance_unchanged',read(out/'baseline_full.json')==read(P55/'baseline_full.json'))
    check('old_run_still_failed',read(R55/'outcome.json')['status']=='no_accepted_sva')
    dump(out/'qualification.json',dict(passed=True,checks=checks,new_model_calls=0,new_native_calls=0,
        local_fixture_scope='Archived actual failed responses plus explicitly local measured controls; never new model results.'))
    dump(out/'request.preview.json',req)
    protocol=read(P55/'protocol.json');protocol.update(scope='research56_fresh_op_novelty',request_sha256=old.digest(out/'request.preview.json'),
        stage_order=['strict_interface','order_independent_novelty','native_development_alignment','full151_native_acceptance'],
        initial_context_change='Only fixed original model BRANCH shown as current. Failed OP templates withheld, while original RTL, verified OP model plan and real native development feedback retained.',
        comparison_limit='Changed generation context; not a controlled attribution of mechanism benefit.')
    dump(out/'protocol.json',protocol)
    snap=out/'source_snapshot';snap.mkdir()
    for p in [Path(__file__),*[ROOT/'scripts'/n for n in read(P55/'source_hashes.json')]]:shutil.copy2(p,snap/p.name)
    dump(out/'source_hashes.json',{p.name:old.digest(p) for p in snap.iterdir()})
    dump(out/'sealed.json',{p.relative_to(out).as_posix():old.digest(p) for p in out.rglob('*') if p.is_file() and p.suffix in ('.json','.py','.sv','.sva')})
    print('FRESH_OP_PREPARED',len(checks),'checks; new model/native0',flush=True)


def run(prep,out,auth):
    # Only the real model adapter changes. All original native stages and the
    # complete151 acceptance rule execute through the unchanged research55 run.
    with patch.object(previous,'Model',Model):previous.run(prep,out,auth)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
