"""Bounded O versus added-history pilot with editable BRANCH/OP components.

prepare/verify make no model calls. run requires a new purpose-bound grant.
Local native qualification fixtures never enter model requests.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import time

import research135_editable_history_qualification as q
import research69_deadline_transport as transport

x,s=q.x,q.s
ROOT,read,dump,digest,rel=q.ROOT,q.read,q.dump,q.digest,q.rel
SEED=13607
PURPOSE='research136_editable_history_prospective_pilot'
QUAL=ROOT/'deliverables/research135_qualification_20261026_r01'
INV=ROOT/'deliverables/research135_inventory_20261026_r01'


def request(candidate,records,folder,history,iteration):
    req=s.payload(candidate,records,folder,history,iteration)
    body=json.loads(req['messages'][1]['content'])
    for key in ('current_op','fixed_component','component_binding','current_op_ids','component_contract','limits'):
        body.pop(key,None)
    body['current_assertions']=[{k:a[k] for k in q.FIELDS} for a in candidate['assertions']]
    body['current_candidate_status']='Partial or rejected development candidate; not a complete accepted solution. Every component is editable, including BRANCH.'
    body['task']='Return the entire BRANCH and OP assertion set. Repair the supplied current missed checks while retaining correct instruction applicability, legal behavior and earlier protection. Choose every predicate and timing yourself. No component is copied or repaired by the framework.'
    body['output_contract']='JSON object with exactly operation,reason,assertions. operation=replace; reason string. assertions array length2..6. Each item has exactly antecedent,consequent,timing,obligations; text expressions, timing same_sample or next_sample. First item labels illegal_branch_persists; remaining items label op_bit28_illegal. Each obligations is a one-element list. All predicates including the first BRANCH item are editable. Native labels are positional only. Signals instr,instr_new,illegal_insn,rv32e,rv32m and supported sampled functions. No declarations or preassembled property fields.'
    body['acceptance']='Both policies use identical interface, public current9 plus search36 native gates, required first/held triggers, all-property guards and independent instruction decoding. The history policy additionally evaluates full151 historical protection. Unknown never passes. Labels do not establish detection; actual native behavior does. No independent tests are supplied.'
    req['messages'][0]['content']='Generate the complete SVA assertion set as the specified JSON textual expressions. All components are editable. Use only the supplied RTL, specifications and actual development observations; no local semantic repair will be applied.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    req.update(model=s.MODEL,seed=SEED+iteration,temperature=0.2,max_tokens=1024)
    return req


def branch(status,measured,ordinary,historical,lost,new_false,critical_unknown=0):
    if status!='response_received':return 'stop_transport'
    if not measured:return 'stop_interface_or_repeat'
    if critical_unknown:return 'stop_unknown'
    if not ordinary:return 'stop_ordinary_rejects'
    if historical:return 'stop_both_accept_no_discrimination'
    if not (lost or new_false):return 'stop_history_gap_without_actual_regression'
    return 'history_once'


class Budget:
    def __init__(self):self.entries=[]
    def reserve(self,path,req,first_branch=None):
        i=len(self.entries)
        if i>=2:raise ValueError('physical_call_cap')
        if path!=('shared/v0' if i==0 else 'history/v1'):raise ValueError('wrong_path')
        if i and first_branch!='history_once':raise ValueError('no_qualified_regression')
        if req['model']!=s.MODEL or req['seed']!=SEED+i or req['temperature']!=0.2 or req['max_tokens']!=1024:raise ValueError('model_sampling_changed')
        # Conservative UTF8-byte reservation, not claimed as measured tokens.
        reserve=sum(len(m['content'].encode()) for m in req['messages'])+2048+1024
        if reserve>40000 or sum(e['reservation'] for e in self.entries)+reserve>80000:raise ValueError('reserved_budget')
        self.entries.append(dict(path=path,request_sha256=x.old.acceptance.sha(req),reservation=reserve,reserved_at=time.time()))


def controller_tests(req):
    checks=[]
    for status in ('response_received','timeout','http_error'):
        for measured in (False,True):
            for o in (False,True):
                for h in (False,True):
                    for lost,fp in ((0,0),(1,0),(0,1)):
                        result=branch(status,measured,o,h,lost,fp)
                        yes=status=='response_received' and measured and o and not h and bool(lost or fp)
                        assert (result=='history_once')==yes
                        checks.append([status,measured,o,h,lost,fp,result])
    assert branch('response_received',True,True,False,1,0,1)=='stop_unknown'
    b=Budget();b.reserve('shared/v0',req)
    second=copy.deepcopy(req);second['seed']+=1
    b.reserve('history/v1',second,'history_once')
    try:b.reserve('history/v1',second,'history_once')
    except ValueError:checks.append('third_attempt_rejected')
    else:raise AssertionError('third_attempt')
    for reason in ('stop_both_accept_no_discrimination','stop_history_gap_without_actual_regression','stop_transport'):
        b=Budget();b.reserve('shared/v0',req)
        try:b.reserve('history/v1',second,reason)
        except ValueError:checks.append(reason+'_blocked')
        else:raise AssertionError(reason)
    return checks


def verify(prep):
    for name,h in read(prep/'sealed.json').items():assert digest(prep/name)==h,name
    for name,h in read(prep/'source_bindings.json').items():assert digest(ROOT/name)==h,name
    assert controller_tests(read(prep/'request.preview.json'))==read(prep/'controller_checks.json')


def prepare(out):
    opened=q.guard()
    for name,h in read(QUAL/'sealed.json').items():assert digest(QUAL/name)==h,name
    assert read(QUAL/'outcome.json')['qualified']
    out.mkdir(parents=True,exist_ok=False)
    initial=read(QUAL/'initial.json');baseline=read(QUAL/'baseline_full.json')
    dump(out/'initial.json',initial);dump(out/'baseline_full.json',baseline)
    dump(out/'candidate_matrix.json',read(QUAL/'candidate_matrix.json'))
    dump(out/'selection.json',read(QUAL/'selection.json'))
    native=QUAL/'native_controls/baseline/native'
    records={k:read(native/k/'result.json') for k in ('alignment','search','history')}
    req=request(initial,records,native,False,0)
    dump(out/'request.preview.json',req)
    for arm in ('O','H'):dump(out/'arms'/arm/'request.preview.json',req)
    body=json.loads(req['messages'][1]['content'])
    assert set(body['actual_feedback']['visible_counts'])=={'alignment','search'}
    assert not any(k in body for k in ('fixed_component','current_op','component_contract'))
    assert body['current_assertions'][0]['antecedent']==initial['assertions'][0]['antecedent']
    checks=controller_tests(req);dump(out/'controller_checks.json',checks)
    protocol=dict(name=PURPOSE,created=time.time(),status='sealed_awaiting_new_explicit_authorization',
        estimand='Added historical checks versus ordinary acceptance on the SAME fresh shared proposal; conditional one-call history recovery. No unique R-over-H claim, no random generation population rate.',
        source_population=rel(INV/'population_lock.json'),selection=read(out/'selection.json'),
        common_generation='DeepSeek V3-0324, same text expressions, sample/transaction-bound development feedback and existing decoded-rule assistance for both policies; full-set original research51 renderer makes BRANCH editable. This common capability/interface change is not a core-mechanism benefit. No new plan stage.',
        rules=dict(O='Unchanged research66 ordinary: current9 and acquired search36, first/held requirements, native sampling, independent oracle, no false alarm/miss/unknown, all-property guards.',
                   H='Same O plus unchanged full151 absolute acceptance and all-property historical guard. Also record lost baseline detections and new false alarms. H/R semantic equivalence in this fixed corpus is retained; no third R arm.'),
        shared='One fresh shared proposal, one native measurement for both decisions. Archived fixtures/candidates never substituted as first proposal.',
        editable_components='BRANCH a0 and every OP component are editable. Labels retained for existing phase checker; no immutable property. Ordinary native rules still require both obligations on public evidence.',
        continuation='Only a healthy measured shared proposal with O=true,H=false, critical unknown=0 and confirmed lost baseline detection or new legal false alarm qualifies. O accepts/stops; H rejects and retains exact initial active hash, then gets ONE actual history-feedback call. H-only missing previous OP targets without regression does not qualify.',
        targets='Full151: 420 OP and270 BRANCH finite violation/config/sample points, plus current9 phase gate; missing exposure/required trigger or unknown rejects. Baseline has partial270 BRANCH protection, not whole-case acceptance.',
        information='First public current9/search36 only; history measured privately for both rules. Only H continuation gets its own history diagnosis through same builder. No hand-written positive/negative fixture, other successful archived solution or independent data in requests.',
        model=s.MODEL,endpoint=transport.DEFAULT_URL,seeds=[SEED,SEED+1],temperature=0.2,max_output_tokens=1024,
        maximum_physical_model_calls=2,maximum_calls_per_trajectory=2,maximum_recovery_calls=1,
        maximum_reserved_per_call=40000,total_reserved=80000,call_timeout_seconds=300,max_wall_seconds=1200,
        retries=0,quota_transfer=False,native_compile_cap=16,native_experiment_cap=16,native_smoke_cap=16,
        costs='Shared generation counted once physically and once logically per trajectory. O stops after acceptance; equal maximum budgets do not imply equal actual cost. Record attempted calls/errors and actual token/native/reference costs; unavailable usage stays null.',
        stop='No discrimination, no actual regression, O rejection, interface/repeat failure, unknown, transport failure or exhausted budget stops. No replacement candidate, reseeding, extra call or automatic expansion.',
        fallback='Record before/proposal/active hashes separately; H rejection keeps previous accepted partial baseline even while failed proposal is sent for repair.',
        independent='Only after H recovery passes unchanged complete151 gates: freeze O and H terminal versions together, then draw96 new instruction words/four configs, exclude all existing instruction input words. Test BOTH terminals; never choose versions using test results. No independent test or success implied by qualification.',
        post_test='No candidate changes. If later used for refinement, promote entire related batch to development. Any future expansion needs a new sealed protocol and authorization.',
        research133='FIFO independent inputs/outcomes never read or used; remain independent.',
        funding='No model budget available in preparation. Request fresh max2 calls ONLY after seal; no old purpose-limited quota transfer.')
    dump(out/'protocol.json',protocol)
    dump(out/'model_config.json',dict(remote_url=transport.DEFAULT_URL,remote_model=s.MODEL,
        max_model_calls=2,max_tokens=80000,max_wall_seconds=1200,call_timeout=300,
        options=dict(seed=SEED,temperature=0.2,num_predict=1024)))
    for n in ('source_binding.json','history_cases.json','search_cases.json'):shutil.copy2(q.P/n,out/n)
    for rev in ('before','after'):shutil.copytree(q.P/rev,out/rev)
    # Don't copy or inspect old heldout exclusion files while choosing rules.
    dump(out/'independence_policy.json',dict(test_inputs_read=False,after_terminal_only='Gather existing independent_cases.json instruction integers for collision exclusion, never labels/outcomes; combine with all development words before new generation.'))
    dump(out/'checks.json',dict(passed=True,controller_cases=len(checks),same_shared_request=read(out/'arms/O/request.preview.json')==read(out/'arms/H/request.preview.json'),
        no_history_in_first_feedback=True,editable_branch_verified=True,model_calls=0,new_independent_tests=0))
    dump(out/'read_audit.json',sorted(opened))
    paths=list((ROOT/'scripts').glob('*.py'))+[QUAL/'sealed.json',INV/'sealed.json',QUAL/'initial.json',QUAL/'baseline_full.json']
    dump(out/'source_bindings.json',{rel(p):digest(p) for p in paths})
    (out/'SUMMARY.md').write_text('# research136 前瞻性历史检查先导封存\n\n候选全集及排除理由见candidate_matrix.json，范围为7个去重Ibex候选和9个FIFO历史候选；3个Ibex合格，按封存顺序选原共享基线，未按区分结果选候选。FIFO因不同父案例/接口暂缓，不表示其质量不合格。\n\nBRANCH和OP均可编辑；普通current9/search36与完整151历史规则不变。新增接口自由度属于公共生成能力条件，不算创新收益。H/R在该固定语料上等价，仅比较O/H。\n\n本地夹具已原生确认O接受/H拒绝且丢失历史保护；夹具不是模型提案，不发送模型。真实新提案尚未生成，额外拒绝、恢复、独立通过均尚未测量。\n\n封存最多2次DeepSeek V3-0324调用：共享新提案1次，仅普通接受/历史拒绝并有确认退化时恢复1次。旧缺口仍缺失不自动算退化。失败、无机会、超时、重复、关键unknown立即停，不加种子。恢复完整接受后先冻结两组再生成96字新独立测试。\n\nresearch133未读、未改、未参与设计。模型调用0；需新的明确授权，未调用远程服务。\n',encoding='utf-8')
    dump(out/'sealed.json',{p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file() and p.name!='sealed.json'})
    verify(out)
    print('SEALED136',len(checks),'controller checks; max2 calls awaiting authorization',flush=True)


class Model(transport.RemoteModel):
    def _payload(self,*args):return self.pending_request
    def save_decoded_output(self,folder,value,current,secret):
        candidate=q.adapt(value,current)
        dump(folder/'candidate.json',candidate)
        (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n')
        return candidate,'model_full_set_exact_expressions_all_components_editable'


def run(prep,out,authorization):
    verify(prep);grant=read(authorization)
    assert grant['purpose']==PURPOSE and type(grant['authorized_calls']) is int and grant['authorized_calls']==2
    assert grant['endpoint']==transport.DEFAULT_URL and grant['model']==s.MODEL
    assert grant['prepared_sha256']==digest(prep/'sealed.json') and grant['run_output']==rel(out)
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'authorization.json',grant)
    initial=read(prep/'initial.json');baseline=read(prep/'baseline_full.json')
    active={'O':initial,'H':initial};model=Model(out/'service',read(prep/'model_config.json'));budget=Budget()
    native_folder=QUAL/'native_controls/baseline/native'
    records={k:read(native_folder/k/'result.json') for k in ('alignment','search','history')}
    state='not_started';first=None;recovered=False;tests=None;complete=False
    def dispatch(path,current,rec,folder,history,iteration,why=None):
        req=request(current,rec,folder,history,iteration)
        if not iteration:assert req==read(prep/'request.preview.json')
        budget.reserve(path,req,why);dump(out/'budget_ledger.json',budget.entries)
        model.pending_request=req
        call,candidate=model.call(out/path/'model_call',current,'both_obligations',{},'prospective_history')
        ev=measured=None
        if candidate is not None and x.signature(candidate) not in {x.signature(initial),x.signature(current)}:
            ev,measured=x.evaluate(candidate,out/path/'native',baseline)
            q.inspect_version(out/path/'native',candidate,baseline)
        elif candidate is not None:
            dump(out/path/'repeat_rejection.json',dict(reason='same_executable_predicate_set'));candidate=None
        return call,candidate,ev,measured
    try:
        call,c,ev,rec=dispatch('shared/v0',initial,records,native_folder,False,0)
        o=bool(ev and ev['ordinary']['accepted']);h=bool(ev and ev['full_absolute'])
        state=branch(call['status'],ev is not None,o,h,len(ev['lost_detection_ids']) if ev else 0,
            len(ev['new_false_alarm_ids']) if ev else 0,
            sum(v['unknown'] for v in ev['counts'].values()) if ev else 0)
        first=dict(O=o,H=h,branch=state,measured=ev is not None)
        dump(out/'first_decisions.json',first)
        for arm,accepted in (('O',o),('H',h)):
            active[arm]=x.journal(out/'arms'/arm/'v0',initial,c,accepted,dict(rule=arm,accepted=accepted,branch=state))
        if state=='history_once':
            call,c2,ev2,rec2=dispatch('history/v1',c,rec,out/'shared/v0/native',True,1,state)
            recovered=bool(ev2 and ev2['full_absolute'])
            active['H']=x.journal(out/'arms/H/v1',active['H'],c2,recovered,dict(rule='H',accepted=recovered))
            state='recovered_full151' if recovered else 'stop_recovery_failed'
        dump(out/'terminal_versions.json',{a:x.old.acceptance.sha(c) for a,c in active.items()})
        if recovered:
            # Freeze before reading heldout input integers for collision checks.
            dump(out/'terminal_freeze.json',dict(time=time.time(),versions=read(out/'terminal_versions.json')))
            exclude={r['sample']['instruction'] for r in baseline['ledger']}
            exclude.update(r['sample']['instruction'] for r in records['alignment']['ledger'])
            # Windows rg indexes filenames only; no outcomes or FIFO133 read.
            cmd=['powershell.exe','-NoProfile','-Command','rg --files deliverables -g independent_cases.json']
            proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,check=True)
            sources=[]
            for name in sorted(set(proc.stdout.splitlines())):
                path=ROOT/name.replace('\\','/')
                if 'research133_' in str(path) or 'research134_' in str(path):continue
                obj=read(path)
                if isinstance(obj,list):
                    words={t['instruction'] for t in obj if isinstance(t,dict) and type(t.get('instruction')) is int}
                    exclude.update(words);sources.append(dict(path=rel(path),sha256=digest(path),words=len(words)))
            # Same phase-qualified96/four-config generator. Do not mutate prep.
            terminal=out/'test_configuration';terminal.mkdir()
            dump(terminal/'excluded_words.json',sorted(exclude));dump(out/'exclusion_sources.json',sources)
            shutil.copy2(prep/'source_binding.json',terminal/'source_binding.json')
            for rev in ('before','after'):shutil.copytree(prep/rev,terminal/rev)
            s.old.prior.p.independent(terminal,out,active)
            tests=read(out/'independent_summary.json')
        complete=True
    finally:
        dump(out/'cost.json',x.costs.native_cost(out))
        dump(out/'outcome.json',dict(completed=complete,first=first,status=state,actual_model_calls=len(budget.entries),
            recovered_full151=recovered,independent=tests,
            qualified_chain=bool(recovered and tests and tests['H']['passed']),automatic_expansion=False,
            recovery_rate_estimable=bool(first and first['branch']=='history_once'),research133_unused=True))
        verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','verify','run'))
    for n in ('out','prepared','authorization'):ap.add_argument('--'+n,type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED136; model0')
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
