"""Prospective O/H pilot using label-bound mapping throughout the controller.

prepare/verify are local only. run requires a new purpose/seal/output-bound grant.
Local integration tests use a separately labeled backend, never real-model data.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import time
from unittest.mock import patch
import research139_obligation_mapping as mapping
import research140_mapping_qualification as qualification

p = mapping.prior
x, ROOT, read, dump, digest, rel = p.x, p.ROOT, p.read, p.dump, p.digest, p.rel
SEED = 14207
PURPOSE = 'research142_label_mapped_prospective_history_pilot'
QUAL_PREP = ROOT/'deliverables/research140_mapping_prepare_20261027_r01'
QUAL_RUN = ROOT/'deliverables/research140_mapping_native_20261027_r01'
QUAL_AUDIT = ROOT/'deliverables/research141_mapping_audit_20261027_r01'
OLD_PREP = qualification.PREVIOUS
BASE_NATIVE = p.QUAL/'native_controls/baseline/native'


def request(candidate, records, folder, history, iteration):
    req = mapping.request(candidate, records, folder, history, iteration)
    req['seed'] = SEED + iteration
    return req


class Budget:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.entries, self.native = [], []

    def check_time(self):
        if self.clock()-self.started >= 1200:
            raise ValueError('wall_budget_exhausted')

    def reserve(self, path, req, first_branch=None):
        self.check_time()
        i = len(self.entries)
        if i >= 2: raise ValueError('physical_call_cap')
        if path != ('shared/v0' if i == 0 else 'history/v1'): raise ValueError('wrong_path')
        if i and first_branch != 'history_once': raise ValueError('no_qualified_regression')
        if (req['model'], req['seed'], req['temperature'], req['max_tokens']) != (p.s.MODEL, SEED+i, 0.2, 1024):
            raise ValueError('model_sampling_changed')
        amount = sum(len(v['content'].encode()) for v in req['messages']) + 2048 + 1024
        if amount > 40000 or sum(e['reservation'] for e in self.entries)+amount > 80000:
            raise ValueError('reserved_budget')
        self.entries.append(dict(path=path, request_sha256=x.old.acceptance.sha(req),
                                 reservation=amount, reserved_at=time.time()))

    def reserve_native(self, path, recovered=False):
        self.check_time()
        allowed = {'shared/v0':6, 'history/v1':6, 'independent':4}
        if path not in allowed or any(e['path']==path for e in self.native):
            raise ValueError('native_path_or_repeat')
        if path == 'independent':
            if not recovered or len(self.entries)!=2 or len(self.native)!=2:
                raise ValueError('independent_before_complete_recovery')
        elif not self.entries or self.entries[-1]['path'] != path:
            raise ValueError('native_before_dispatch')
        amount = allowed[path]
        if sum(e['compiles'] for e in self.native)+amount > 16:
            raise ValueError('native_cap')
        self.native.append(dict(path=path, compiles=amount, executions=amount, reserved_at=time.time()))

    def save(self, out):
        dump(out/'budget_ledger.json', self.entries)
        dump(out/'native_reservations.json', self.native)


def controller_checks(req):
    checks=[]
    for status in ('response_received','timeout','http_error'):
        for measured in (False,True):
            for o in (False,True):
                for h in (False,True):
                    for lost, fp in ((0,0),(1,0),(0,1)):
                        for unknown in (0,1):
                            result=p.branch(status,measured,o,h,lost,fp,unknown)
                            expected=status=='response_received' and measured and o and not h and bool(lost or fp) and not unknown
                            assert (result=='history_once')==expected
                            checks.append([status,measured,o,h,lost,fp,unknown,result])
    def rejects(name, operation):
        try: operation()
        except ValueError: checks.append(name)
        else: raise AssertionError(name)
    second=copy.deepcopy(req);second['seed']+=1
    b=Budget();b.reserve('shared/v0',req);b.reserve_native('shared/v0')
    b.reserve('history/v1',second,'history_once');b.reserve_native('history/v1')
    b.reserve_native('independent',True)
    assert sum(e['compiles'] for e in b.native)==16
    rejects('third_call',lambda:b.reserve('history/v1',second,'history_once'))
    rejects('duplicate_native',lambda:b.reserve_native('independent',True))
    rejects('native_without_call',lambda:Budget().reserve_native('shared/v0'))
    rejects('independent_without_recovery',lambda:Budget().reserve_native('independent',False))
    for reason in ('stop_interface_or_repeat','stop_ordinary_rejects','stop_both_accept_no_discrimination',
                   'stop_history_gap_without_actual_regression','stop_transport','stop_unknown'):
        b=Budget();b.reserve('shared/v0',req)
        rejects(reason,lambda:b.reserve('history/v1',second,reason))
    for key, val in [('model','different'),('seed',SEED+5),('max_tokens',2048),('temperature',0.7)]:
        bad=copy.deepcopy(req);bad[key]=val
        rejects('bad_'+key,lambda:Budget().reserve('shared/v0',bad))
    large=copy.deepcopy(req);large['messages'][1]['content']='x'*40001
    rejects('too_large',lambda:Budget().reserve('shared/v0',large))
    now=[0];b=Budget(clock=lambda:now[0]);now[0]=1200
    rejects('wall_model',lambda:b.reserve('shared/v0',req))
    rejects('wall_native',lambda:b.reserve_native('shared/v0'))
    return checks


class Model(p.transport.RemoteModel):
    def _payload(self,*args): return self.pending_request

    def save_decoded_output(self, folder, value, current, secret):
        candidate=mapping.adapt(value,current)
        dump(folder/'candidate.json',candidate)
        (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n',encoding='utf-8')
        return candidate,'exact_full_set_expressions_label_bound_obligations'


def validate_grant(prep,out,grant):
    assert grant['purpose']==PURPOSE
    assert type(grant['authorized_calls']) is int and grant['authorized_calls']==2
    assert grant['endpoint']==p.transport.DEFAULT_URL and grant['model']==p.s.MODEL
    assert grant['prepared_sha256']==digest(prep/'sealed.json') and grant['run_output']==rel(out)


def physical_cost(out):
    legacy=x.costs.native_cost(out)
    compiles=list(out.rglob('compile.json')); executions=list(out.rglob('execute.json'))
    return dict(model=legacy['total'], native_compiles=len(compiles),native_executions=len(executions),
                compile_seconds=sum(read(f)['wall_seconds'] for f in compiles),
                execute_seconds=sum(read(f)['wall_seconds'] for f in executions),formal_calls=0,
                note='Physical execute.json paths counted once; legacy smoke and execution fields may alias the same command.')


class RealBackend:
    mode='real'
    def __init__(self,prep,out): self.model=Model(out/'service',read(prep/'model_config.json'))
    def generate(self,req,folder,current):
        self.model.pending_request=req
        return self.model.call(folder,current,'both_obligations',{},'prospective_history')
    def evaluate(self,candidate,folder,baseline):
        ev,records=mapping.evaluate(candidate,folder,baseline)
        mapping.inspect_version(folder,candidate,baseline)
        return ev,records,folder
    def independent(self,prep,out,active,baseline,records):
        return independent(prep,out,active,baseline,records)


def critical_unknown(ev):
    if not ev:return 0
    return (sum(v['unknown'] for v in ev['counts'].values())+
            sum(len(g['unknown']) for g in ev['all_property_guards'].values())+
            len(ev['current_gate']['all_property_guard']['unknown']))


def execute(prep,out,backend):
    """Same state machine for real dispatch and explicitly labeled local tests."""
    initial=read(prep/'initial.json');baseline=read(prep/'baseline_full.json')
    records={k:read(BASE_NATIVE/k/'result.json') for k in ('alignment','search','history')}
    active={'O':initial,'H':initial};budget=Budget();first=None;recovered=False;tests=None;complete=False
    state='not_started'
    dump(out/'execution_mode.json',dict(mode=backend.mode,local_test_not_model_experiment=backend.mode!='real'))
    def dispatch(path,current,rec,native_folder,history,iteration,why=None):
        req=request(current,rec,native_folder,history,iteration)
        if iteration==0:assert req==read(prep/'request.preview.json')
        budget.reserve(path,req,why);budget.save(out)
        call,c=backend.generate(req,out/path/'model_call',current)
        ev=measured=None;source=None
        if c is not None and x.signature(c) not in {x.signature(initial),x.signature(current)}:
            budget.reserve_native(path);budget.save(out)
            ev,measured,source=backend.evaluate(c,out/path/'native',baseline)
        elif c is not None:
            dump(out/path/'repeat_rejection.json',dict(reason='same_executable_predicate_set'));c=None
        return call,c,ev,measured,source
    try:
        call,c,ev,rec,source=dispatch('shared/v0',initial,records,BASE_NATIVE,False,0)
        o=bool(ev and ev['ordinary']['accepted']);h=bool(ev and ev['full_absolute'])
        state=p.branch(call['status'],ev is not None,o,h,len(ev['lost_detection_ids']) if ev else 0,
                       len(ev['new_false_alarm_ids']) if ev else 0,critical_unknown(ev))
        first=dict(O=o,H=h,branch=state,measured=ev is not None)
        dump(out/'first_decisions.json',first)
        for arm,accepted in (('O',o),('H',h)):
            active[arm]=x.journal(out/'arms'/arm/'v0',initial,c,accepted,dict(rule=arm,branch=state))
        if state=='history_once':
            call,c2,ev2,rec2,source2=dispatch('history/v1',c,rec,source,True,1,state)
            recovered=bool(ev2 and ev2['full_absolute'] and not critical_unknown(ev2))
            active['H']=x.journal(out/'arms/H/v1',active['H'],c2,recovered,dict(rule='H',accepted=recovered))
            state='recovered_full151' if recovered else 'stop_recovery_failed'
        dump(out/'terminal_versions.json',{a:x.old.acceptance.sha(c) for a,c in active.items()})
        if recovered:
            budget.reserve_native('independent',True);budget.save(out)
            for arm,candidate in active.items():dump(out/'terminal_frozen'/arm/'candidate.json',candidate)
            dump(out/'terminal_freeze.json',dict(time=time.time(),versions=read(out/'terminal_versions.json'),
                                               local_test=backend.mode!='real'))
            tests=backend.independent(prep,out,active,baseline,records)
        complete=True
    except Exception as exc:
        # Avoid exception messages potentially containing provider/request data.
        dump(out/'exception.json',dict(type=type(exc).__name__,stage=state,retries=0))
        raise
    finally:
        budget.save(out)
        actual=len(list(out.rglob('attempt.json'))) if backend.mode=='real' else 0
        dump(out/'cost.json',physical_cost(out))
        dump(out/'outcome.json',dict(completed=complete,mode=backend.mode,first=first,status=state,
            actual_model_calls=actual,reserved_controller_attempts=len(budget.entries),
            recovered_full151=recovered,independent=tests,new_independent_executed=backend.mode=='real' and tests is not None,
            qualified_chain=bool(backend.mode=='real' and recovered and tests and tests['H']['passed']),
            recovery_rate_estimable=bool(backend.mode=='real' and first and first['branch']=='history_once'),
            automatic_expansion=False,research133_unused=True))


def independent(prep,out,active,baseline,records):
    """Only called after full recovery and terminal freeze; no old outcomes read."""
    assert (out/'terminal_freeze.json').exists()
    frozen=read(out/'terminal_freeze.json')
    assert frozen['versions']=={a:x.old.acceptance.sha(c) for a,c in active.items()}
    excluded={r['sample']['instruction'] for r in baseline['ledger']}
    excluded.update(r['sample']['instruction'] for r in records['alignment']['ledger'])
    proc=subprocess.run(['powershell.exe','-NoProfile','-Command','rg --files deliverables -g independent_cases.json'],
                        cwd=ROOT,capture_output=True,text=True,check=True)
    sources=[]
    for name in sorted(set(proc.stdout.splitlines())):
        f=ROOT/name.replace('\\','/')
        if any(s in str(f) for s in ('research133_','research134_')):continue
        values=read(f)
        if isinstance(values,list):
            words={v['instruction'] for v in values if isinstance(v,dict) and type(v.get('instruction')) is int}
            excluded.update(words);sources.append(dict(path=rel(f),sha256=digest(f),word_count=len(words)))
    config=out/'test_configuration';config.mkdir()
    dump(config/'excluded_words.json',sorted(excluded));dump(out/'exclusion_sources.json',sources)
    shutil.copy2(prep/'source_binding.json',config/'source_binding.json')
    for rev in ('before','after'):shutil.copytree(prep/rev,config/rev)
    # Existing generator and raw audit are already obligation-projected, not a0
    # based. Summarizer keeps both obligations/configurations actually exposed.
    p.s.old.prior.p.independent(config,out,active)
    for arm,candidate in active.items():
        mapping.validate_ledger(read(out/'frozen'/arm/'independent/result.json'),candidate)
        assert x.old.acceptance.sha(candidate)==frozen['versions'][arm]
    return read(out/'independent_summary.json')


def verify(prep):
    for name,sha in read(prep/'sealed.json').items():assert digest(prep/name)==sha,name
    for name,sha in read(prep/'source_bindings.json').items():assert digest(ROOT/name)==sha,name
    assert controller_checks(read(prep/'request.preview.json'))==read(prep/'controller_checks.json')


def prepare(out):
    opened=p.q.guard();qualification.verify(QUAL_PREP)
    for root in (QUAL_RUN,QUAL_AUDIT):
        for name,sha in read(root/'sealed.json').items():assert digest(root/name)==sha,name
    assert read(QUAL_RUN/'outcome.json')['passed'] and read(QUAL_AUDIT/'audit.json')['passed']
    out.mkdir(parents=True,exist_ok=False)
    for name in ('initial.json','baseline_full.json','candidate_matrix.json','selection.json','source_binding.json','history_cases.json','search_cases.json'):
        shutil.copy2(OLD_PREP/name,out/name)
    for rev in ('before','after'):shutil.copytree(OLD_PREP/rev,out/rev)
    initial=read(out/'initial.json');records={k:read(BASE_NATIVE/k/'result.json') for k in ('alignment','search','history')}
    req=request(initial,records,BASE_NATIVE,False,0)
    dump(out/'request.preview.json',req)
    for arm in ('O','H'):dump(out/'arms'/arm/'request.preview.json',req)
    checks=controller_checks(req);dump(out/'controller_checks.json',checks)
    protocol=read(OLD_PREP/'protocol.json')
    protocol.update(name=PURPOSE,created=time.time(),status='sealed_local_integration_no_model_authorization',seeds=[SEED,SEED+1],
        editable_components='All BRANCH and OP properties editable, any order, multiple per obligation; 2..6 total, exactly one known obligation per property, both obligations required. IDs bind native markers only.',
        integration=dict(adapter='research139.adapt',native='research139.evaluate',audit='research139.inspect_version',
                         feedback='research139.request + fixed new seed',controller=Path(__file__).name),
        common_generation='Same DeepSeek text expression pipeline and development information. Label-bound common interface is infrastructure, not a mechanism benefit. No archival success or local qualification fixtures in requests.',
        critical_unknown='Unknown in ledger OR all-property guards blocks continuation and acceptance.',
        native_compile_cap=16,native_experiment_cap=16,native_smoke_cap=0,
        enforced_native_reservations='6 compiles/executions per fresh candidate, max2; 4 for independent O/H after complete recovery. Inline bench executions are not counted twice as smoke.',
        time_enforcement='Before each model/native stage, max1200s elapsed; each model call has300s deadline, no retry.',
        local_validation='Same execute state machine tested using explicitly labeled local backend with original native records; no fake model success, no independent tests generated locally.',
        funding='No model authorization for this protocol. Any real run requires new purpose/seal/output-bound max2 grant. Old conditional quota cannot be transferred automatically.',
        prior_results='research136 remains interface failure. research140 archived response replay remains retrospective; not a new prospective proposal. research133 remains independent.')
    dump(out/'protocol.json',protocol)
    config=read(OLD_PREP/'model_config.json');config['options']['seed']=SEED
    dump(out/'model_config.json',config)
    dump(out/'read_audit.json',sorted(opened))
    paths=list((ROOT/'scripts').glob('*.py'))+[root/'sealed.json' for root in (OLD_PREP,QUAL_PREP,QUAL_RUN,QUAL_AUDIT)]
    # Bind actual baseline/native source files and RTL used by runtime, not just
    # filenames inside a transitive manifest.
    paths += [f for f in BASE_NATIVE.rglob('*') if f.is_file() and 'obj_dir' not in f.parts]
    paths += [f for f in x.P.glob('*.json') if not any(v in f.name for v in ('excluded','protected_records'))]
    paths += [x.P/rev/name for rev in ('before','after') for name in ('ibex_decoder.sv','ibex_defines.sv')]
    dump(out/'source_bindings.json',{rel(f):digest(f) for f in sorted(set(paths))})
    dump(out/'sealed.json',{f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file()})
    verify(out)
    print('SEALED142',len(checks),'controller checks; no model calls',flush=True)


def run(prep,out,authorization):
    verify(prep);grant=read(authorization);validate_grant(prep,out,grant)
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',grant)
    backend=RealBackend(prep,out)
    try:execute(prep,out,backend)
    finally:verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','verify','run'))
    for name in ('prepared','out','authorization'):ap.add_argument('--'+name,type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED142;model0')
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
