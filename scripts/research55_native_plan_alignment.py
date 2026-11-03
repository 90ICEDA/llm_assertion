"""Bind real OP synthesis to native applicability observations before full replay.

No predicate correction or plan-to-property translation. Local controls are never
model output and are excluded from requests. All samples here are development.
"""
import argparse
import copy
import json
import re
import shutil
from pathlib import Path
import research54_complementary_sva as prior

ROOT, old, common = prior.ROOT, prior.old, prior.common
read, dump = prior.read, prior.dump
P54 = ROOT/'deliverables/research54_prepare_20261023_r02'
R54 = ROOT/'deliverables/research54_real_20261023_r01'
ALLOWED = {'instr', 'instr_new', 'illegal_insn', 'rv32m', 'rv32e', '$past', '$stable', '$rose', '$fell'}


def frontend(value, current):
    errors = []
    def error(kind, **details): errors.append(dict(kind=kind, **details))
    if type(value) is not dict or set(value) != {'operation', 'reason', 'assertions'}:
        error('top_level_keys', required=['operation','reason','assertions'],
              received=sorted(value) if type(value) is dict else type(value).__name__)
        return None, dict(accepted=False, errors=errors)
    if value['operation'] != 'replace_op': error('operation_must_be_replace_op')
    if type(value['reason']) is not str: error('reason_must_be_string')
    items = value['assertions']
    if type(items) is not list or not 1 <= len(items) <= 3:
        error('assertions_must_be_array_of_one_to_three')
        return None, dict(accepted=False, errors=errors)
    for index, item in enumerate(items):
        if type(item) is not dict or set(item) != {'antecedent','consequent','timing','obligations'}:
            error('assertion_fields', index=index); continue
        if item['obligations'] != ['op_bit28_illegal']: error('op_obligation_only', index=index)
        if item['timing'] not in ('same_sample','next_sample'): error('unknown_timing', index=index)
        for field in ('antecedent','consequent'):
            expr = item[field]
            if type(expr) is not str:
                error('expression_must_be_string', index=index, field=field); continue
            stripped = re.sub(r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+", '0', expr)
            unknown = set(re.findall(r'\$?[A-Za-z_][A-Za-z_0-9]*', stripped))-ALLOWED
            if unknown: error('undeclared_identifiers', index=index, field=field,
                              names=sorted(unknown), allowed=sorted(ALLOWED))
    if errors: return None, dict(accepted=False, errors=errors)
    try: candidate = prior.assemble(value, current)
    except (AssertionError, TypeError, KeyError, ValueError) as exc:
        return None, dict(accepted=False, errors=[dict(kind='expression_assembly_rejected', exception=type(exc).__name__, detail=str(exc))])
    # Duplicate evidence remains separate from interface validity. For a repeated
    # baseline, run the small native gate once to return concrete failed cycles.
    duplicate = common.duplicates(candidate, current, 'replace')
    return candidate, dict(accepted=True, errors=[], duplicate=duplicate,
                          scope='Interface only; semantics require native alignment and full replay.')


def alignment(candidate, prep, folder):
    result = old.replay(candidate, read(prep/'alignment_cases.json'), 'alignment', folder, prep)
    natives = {rev:read(folder/rev/'result.json') for rev in ('before','after')}
    guard = prior.all_property_guard(result, natives, candidate)
    windows = read(prep/'windows.public.json')
    context = prior.previous.source_check(prep)
    expected = {w['id']:w for w in context['expected']['windows']}
    bindings = []
    for w in windows:
        refs = [r for r in result['reference'] if r['transaction_id']==w['transaction_id']
                and r['phase']==w['phase'] and r['configuration']==w['configuration']]
        match = len(refs)==1
        ref = refs[0] if match else None
        match = match and ref['instruction']==int(w['instruction_hex'],16) and ref['instr_new']==w['instr_new']
        match = match and all(ref['actual'][rev]==w[rev+'_illegal'] for rev in ('before','after'))
        required = expected[w['id']]['op_applicable']
        rows = [r for r in result['ledger'] if ref and r['sample']['sample_id']==ref['sample_id']
                and r['configuration']==w['configuration']]
        triggered = len(rows)==2 and all(any(a['trigger'] for a in r['native']['assertions'] if a['id']!='a0') for r in rows)
        bindings.append(dict(window=w['id'],source_sample_id=w['sample_id'],
            replay_sample_id=ref['sample_id'] if ref else None,original_sampling_matches=bool(match),
            op_required=required,op_triggered_on_both_revisions=triggered,
            accepted=bool(match and (not required or triggered))))
    verdict = dict(accepted=old.admissible(result) and guard['accepted'] and all(w['accepted'] for w in bindings),
        bindings=bindings,counts=result['counts'],required_untriggered=len(result['required_untriggered']),
        all_property_guard=guard,native_status=result['native_status'],
        scope='Finite original RTL development samples, actual covers and failures; not text bit matching or full acceptance.')
    dump(folder/'alignment_gate.json', verdict)
    return result, verdict


def payload(prep, current, feedback):
    req = prior.payload(prep,current,feedback)
    body = json.loads(req['messages'][1]['content'])
    body.pop('output')
    body['response_contract'] = dict(top_level_keys=['operation','reason','assertions'],
        operation='replace_op',reason_type='string',assertions_type='array,1..3 items',
        assertion_keys=['antecedent','consequent','timing','obligations'],
        expression_type='SystemVerilog boolean expression string',
        timing_values=['same_sample','next_sample'],obligations=['op_bit28_illegal'],
        forbidden_wrapper_keys=['output','response'],allowed_identifiers=sorted(ALLOWED))
    body['native_acceptance_contract'] = (
        'Your exact predicates execute on both original decoder revisions. First, native cover/failure observations '
        'on the bound development transactions check that OP-applicable samples really trigger, including held phases, '
        'and detect their actual RTL violations. A correct rule in prose is insufficient. '
        'Then all115 historical plus36 search transactions must pass the unchanged full acceptance gate. '
        'No private oracle output is an assertion input; do not copy RTL port names into the declared assertion interface.')
    req['messages'][1]['content']=json.dumps(body)
    req['seed']=5501
    return req


class Model(prior.Model):
    def __init__(self,out,prep):
        super().__init__(out,prep); self.config['options']['seed']=5501
    def _payload(self,current,target,feedback,phase): return payload(self.prep,current,feedback)
    def save_decoded_output(self,folder,value,current,secret):
        candidate, verdict = frontend(value,current)
        dump(folder/'interface_gate.json',verdict)
        if candidate is None: return None,'interface_rejected_with_structured_diagnostics'
        assert candidate['assertions'][0]==read(self.prep/'protected_branch.json')
        dump(folder/'candidate.json',candidate)
        (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n')
        return candidate,'exact_model_op_plus_immutable_branch_native_gate_pending'


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    for n,h in read(P54/'sealed.json').items(): assert old.digest(P54/n)==h,n
    for n,h in read(P54/'source_hashes.json').items(): assert old.digest(ROOT/'scripts'/n)==h,n
    for rev in ('before','after'): shutil.copytree(P54/rev,out/rev)
    for name in ('windows.public.json','decoded.public.json','expected.private.json','native_binding.json',
                 'shared_initial.json','source_binding.json','history_cases.json','search_cases.json','development_manifest.json',
                 'baseline_full.json','protected_branch.json','component_binding.json','component_certificate.json'):
        shutil.copy2(P54/name,out/name)
    for cohort in ('history','search'): dump(out/f'baseline/{cohort}/result.json',read(P54/f'baseline/{cohort}/result.json'))
    prior.components(out)
    ids={w['transaction_id'] for w in read(out/'windows.public.json')}
    txns=[t for t in read(out/'search_cases.json') if t['id'] in ids]
    assert len(txns)==len(ids) and len(txns)>0
    dump(out/'alignment_cases.json',txns)
    current=read(out/'shared_initial.json'); checks=[]
    def check(name,ok): checks.append(dict(name=name,passed=bool(ok))); assert ok,name
    failures=[]; failure_files={}
    for version in ('v0','v1'):
        path=R54/version/'model_call/model_edit.json'; value=read(path)
        candidate, verdict=frontend(value,current)
        check('actual_research54_rejected/'+version,candidate is None and not verdict['accepted'])
        failures.append(dict(version=version,actual_model_proposal=value,structured_interface_diagnosis=verdict,
            original_decision=read(R54/version/'decision.json')))
        for name in ('model_edit.json','response.assembled.json','response.stream.raw'):
            p=path.parent/name;failure_files[p.relative_to(ROOT).as_posix()]=old.digest(p)
    dump(out/'failure_binding.json',failure_files)
    feedback=dict(previous_real_attempts=failures,native_development_feedback=read(P54/'initial_feedback.json'))
    dump(out/'initial_feedback.json',feedback)
    # Explicit local controls, never copied into a request or a model result.
    good=old.assemble(dict(operation='replace',reason='LOCAL CONTROL ONLY',assertions=[
        dict(antecedent="instr[6:0]==7'h33 && instr[28]",consequent='illegal_insn',timing='same_sample',obligations=['op_bit28_illegal'])]),None)
    good['assertions'][0]['id']='a1';good['assertions'].insert(0,copy.deepcopy(current['assertions'][0]))
    phase=copy.deepcopy(good);a=phase['assertions'][1]
    a['antecedent']='('+a['antecedent']+') && instr_new';a['property']='('+a['antecedent']+') |-> ('+a['consequent']+')'
    tautology=copy.deepcopy(good);a=tautology['assertions'][1]
    a['consequent']="1'b1";a['property']='('+a['antecedent']+") |-> (1'b1)"
    for name,candidate,expected_pass in [('correct_local_control',good,True),('real_old_bit31_candidate',current,False),
                                          ('first_phase_only_control',phase,False),('vacuous_consequent_control',tautology,False)]:
        dump(out/f'qualification/{name}/candidate.json',candidate)
        result,gate=alignment(candidate,out,out/f'qualification/{name}/native')
        check('native_gate/'+name,gate['accepted']==expected_pass)
        if name=='real_old_bit31_candidate': check('bit31_required_trigger_miss',gate['required_untriggered']>0 and gate['counts']['misses']>0)
        if name=='vacuous_consequent_control': check('true_consequent_misses_despite_trigger',gate['counts']['misses']>0 and gate['required_untriggered']==0)
        print('ALIGNMENT_CONTROL',name,gate['accepted'],flush=True)
    local=dict(operation='replace_op',reason='local interface control',assertions=[
        {k:good['assertions'][1][k] for k in ('antecedent','consequent','timing','obligations')}])
    check('interface_valid',frontend(local,current)[0] is not None)
    for name,bad in [('wrapper',dict(output=local)),('null',None),('array',[]),('missing',dict(operation='replace_op'))]:
        check('interface_reject/'+name,frontend(bad,current)[0] is None)
    for key,badvalue in [('assertions',None),('reason',False),('operation','replace')]:
        bad=copy.deepcopy(local);bad[key]=badvalue;check('wrong_type_or_operation/'+key,frontend(bad,current)[0] is None)
    for field,badvalue in [('antecedent','instr_new_i'),('consequent','illegal_insn_o'),('timing','later'),('obligations',['illegal_branch_persists'])]:
        bad=copy.deepcopy(local);bad['assertions'][0][field]=badvalue
        check('wrong_assertion/'+field,frontend(bad,current)[0] is None)
    req=payload(out,current,feedback);body=json.loads(req['messages'][1]['content'])
    check('no_control_predicate_in_prompt',good['assertions'][1]['antecedent'] not in json.dumps(req))
    check('no_private_answers_in_prompt',not any(k in body for k in ('expected','expected.private','correct_answers')))
    check('no_wrapper_example','output' not in body and 'response_contract' in body)
    check('all_history_and_search_preserved',len(read(out/'history_cases.json'))==115 and len(read(out/'search_cases.json'))==36)
    dump(out/'qualification.json',dict(passed=True,checks=checks,model_calls=0,controls_not_model_results=True))
    dump(out/'request.preview.json',req)
    dump(out/'protocol.json',dict(scope='research55_native_op_alignment',maximum_calls=2,retries=0,endpoint=old.DEFAULT_URL,
        model=old.DEFAULT_MODEL,request_sha256=old.digest(out/'request.preview.json'),
        stage_order=['strict_interface','native_development_alignment','full151_native_acceptance'],
        acceptance='Repair420 OP points, retain270 BRANCH points; no false positive, critical unknown or missing required trigger.',
        independent_test='Not generated; only after an accepted model version.',
        no_predicate_rewrite=True,no_plan_to_sva=True))
    snap=out/'source_snapshot';snap.mkdir()
    for p in [Path(__file__),*[ROOT/'scripts'/n for n in read(P54/'source_hashes.json')]]:shutil.copy2(p,snap/p.name)
    dump(out/'source_hashes.json',{p.name:old.digest(p) for p in snap.iterdir()})
    dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():old.digest(p) for p in out.rglob('*')
        if p.is_file() and (p.suffix in ('.py','.sv','.json') or p.name=='execute.log')})
    print('NATIVE_ALIGNMENT_PREPARED',len(checks),'checks; model calls0',flush=True)


def run(prep,out,auth_path):
    auth=read(auth_path);protocol=read(prep/'protocol.json')
    assert auth['scope']==protocol['scope'] and auth['authorized_calls']==2 and auth['endpoint']==protocol['endpoint']
    assert auth['request_sha256']==protocol['request_sha256'] and auth['run_output']==out.relative_to(ROOT).as_posix()
    for name,h in read(prep/'sealed.json').items():assert old.digest(prep/name)==h,name
    for name,h in read(prep/'source_hashes.json').items():assert old.digest(ROOT/'scripts'/name)==h,name
    for name,h in read(prep/'failure_binding.json').items():assert old.digest(ROOT/name)==h,name
    prior.components(prep)
    out.mkdir(parents=True,exist_ok=False);shutil.copytree(prep/'source_snapshot',out/'source_snapshot')
    shutil.copy2(auth_path,out/'authorization.json');dump(out/'protocol.json',protocol)
    current=read(prep/'shared_initial.json');baseline=read(prep/'baseline_full.json')
    feedback=read(prep/'initial_feedback.json');model=Model(out,prep);decisions=[];accepted=None;seen=set()
    try:
        for i in range(2):
            folder=out/f'v{i}'
            call,candidate=model.call(folder/'model_call',current,'op_bit28_illegal',feedback,'native_plan_alignment_synthesis')
            raw=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
            if candidate is None:
                diag=read(folder/'model_call/interface_gate.json') if (folder/'model_call/interface_gate.json').exists() else dict(call=call)
                decision=dict(accepted=False,reasons=[dict(kind='interface_or_transport_rejected',details=diag)])
                feedback=dict(previous_feedback=feedback,actual_model_proposal=raw,actual_interface_diagnosis=diag,call=call)
            elif old.acceptance.sha(candidate) in seen:
                decision=dict(accepted=False,reasons=[dict(kind='repeated_rejected_candidate')])
                feedback=dict(previous_feedback=feedback,actual_model_proposal=raw,decision=decision)
            else:
                seen.add(old.acceptance.sha(candidate))
                aligned,gate=alignment(candidate,prep,folder/'alignment')
                if not gate['accepted']:
                    decision=dict(accepted=False,reasons=[dict(kind='native_applicability_or_target_failure')])
                    feedback=dict(actual_model_proposal=raw,native_alignment_gate=gate,native_evidence=old.evidence(aligned),
                        previous_full_development_feedback=read(prep/'initial_feedback.json')['native_development_feedback'])
                else:
                    h=old.replay(candidate,read(prep/'history_cases.json'),'history',folder/'history',prep)
                    s=old.replay(candidate,read(prep/'search_cases.json'),'search',folder/'search',prep)
                    decision=old.decide(baseline,common.combine(h,s))
                    guards={cohort:prior.all_property_guard(result,{rev:read(folder/cohort/rev/'result.json') for rev in ('before','after')},candidate)
                            for cohort,result in [('history',h),('search',s)]}
                    dump(folder/'all_property_guard.json',guards)
                    for cohort,guard in guards.items():
                        if not guard['accepted']:
                            decision['accepted']=False;decision['reasons'].append(dict(kind='all_property_false_alarm_or_unknown',cohort=cohort,details=guard))
                    dump(folder/'mapping.json',dict(history=h['mapping'],search=s['mapping']))
                    feedback=dict(actual_model_proposal=raw,history=old.evidence(h),search=old.evidence(s),decision=common.gate_feedback(decision))
                    if decision['accepted']:
                        accepted=candidate;dump(out/'accepted_candidate.json',candidate)
                        dump(out/'acceptance.json',dict(sha256=old.acceptance.sha(candidate),history=h['counts'],search=s['counts'],decision=decision))
            dump(folder/'decision.json',decision);decisions.append(dict(version=i,accepted=decision['accepted']))
            print('ALIGNED_VERSION',i,decision['accepted'],flush=True)
            if accepted is not None:break
    finally:
        dump(out/'outcome.json',dict(status='accepted_development_only' if accepted else 'no_accepted_sva',
            calls=len(model.calls),decisions=decisions,accepted_candidate_sha256=old.acceptance.sha(accepted) if accepted else None,
            independent_test='not_run',formal_calls=0))
        dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
