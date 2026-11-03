"""Bounded axis_adapter O/H controller. prepare is LOCAL ONLY.

run requires an explicit purpose/seal/output-bound authorization file.
Local state-machine tests replay labeled handwritten native fixtures, never
claiming model calls, real recovery, or new independent-test success.
"""
import argparse
import ast
import copy
import hashlib
import itertools
import json
from pathlib import Path
import random
import re
import time
import research165_adapter_qualification as q
import research69_deadline_transport as transport

P=q.ROOT/'deliverables/research166_adapter_prepare_20261028_r01'
N=q.ROOT/'deliverables/research166_adapter_native_20261028_r01'
R=q.ROOT/'deliverables/research166_adapter_report_20261028_r01'
PURPOSE='research167_original_adapter_bounded_history_pilot'
BRANCH_FILE=q.ROOT/'scripts/research136_prospective_history.py'
tree=ast.parse(BRANCH_FILE.read_text())
branch_node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='branch')
module=ast.Module(body=[branch_node],type_ignores=[]);ast.fix_missing_locations(module)
_ns={};exec(compile(module,str(BRANCH_FILE),'exec'),_ns);branch=_ns['branch']


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def signature(candidate):
    return digest(sorted((re.sub(r'\s+','',a['antecedent']),re.sub(r'\s+','',a['consequent']),a['timing']) for a in candidate))


def adapt(value):
    if not isinstance(value,dict) or set(value)!={'assertions','reason'} or not isinstance(value['reason'],str):raise ValueError('response_schema')
    a=q.validate(value['assertions'])
    # Do not rewrite reserved labels and silently turn invalid output into success.
    if any(v['label'] in {'final','initial','always','begin','end','module','property','assert','wire','logic','input','output','if','else'} for v in a):raise ValueError('reserved_SV_label')
    return copy.deepcopy(a)


def validate_grant(g,seal_hash,run_output):
    assert g['purpose']==PURPOSE and type(g['authorized_calls']) is int and g['authorized_calls']==2
    assert g['endpoint']==transport.DEFAULT_URL and g['model']=='deepseek/deepseek-v3-0324'
    assert g['prepared_sha256']==seal_hash and g['run_output']==run_output


class Model(transport.RemoteModel):
    def _payload(self,*args):return self.pending_request
    def save_decoded_output(self,folder,value,current,secret):
        a=adapt(value);q.dump(folder/'candidate.json',a)
        return a,'model_expressions_preserved_no_semantic_repair'


class Budget:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.start=clock();self.calls=[];self.native=[]
    def time_check(self):
        if self.clock()-self.start>=1200:raise ValueError('wall_budget_exhausted')
    def reserve_call(self,path,req,permission=None):
        self.time_check();i=len(self.calls)
        if i>=2 or path!=('shared' if i==0 else 'recovery'):raise ValueError('call_path_or_cap')
        if i and permission!='history_once':raise ValueError('unqualified_recovery')
        if (req['model'],req['seed'],req['temperature'],req['max_tokens'])!=('deepseek/deepseek-v3-0324',16507+i,0.2,1024):raise ValueError('sampling_changed')
        reserve=sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']
        if reserve>60000 or sum(c['utf8_reservation'] for c in self.calls)+reserve>120000:raise ValueError('reserved_token_cap')
        self.calls.append(dict(path=path,request_hash=digest(req),utf8_reservation=reserve))
    def reserve_native(self,path,recovered=False):
        self.time_check()
        if path not in ('shared','recovery','independent') or path in self.native:raise ValueError('native_path_or_repeat')
        if path=='independent':
            if not recovered or [x['path'] for x in self.calls]!=['shared','recovery'] or self.native!=['shared','recovery']:raise ValueError('independent_before_recovery')
        elif not self.calls or self.calls[-1]['path']!=path:raise ValueError('native_before_call')
        if len(self.native)>=3:raise ValueError('native_cap')
        self.native.append(path)
    def save(self,out):q.dump(out/'budget_ledger.json',dict(reserved_calls=self.calls,native_stages=self.native,compiles_reserved=2*len(self.native)))


def measure(candidate,folder,scenarios,protected=()):
    """Pure rejudgment of actual original-RTL logs; unknown never passes."""
    data={};unknown=[]
    for rev in ('before','after'):
        n=q.read(folder/rev/'result.json')
        if n['compile_status']!='passed' or n['execution_status']!='completed':unknown.append(rev+':native_incomplete');continue
        vals=q.old.trace(folder/rev)
        if len(vals)!=96*len(scenarios) or any(v['cycle']!=i or v['sid']!=i//96 for i,v in enumerate(vals)):
            unknown.append(rev+':trace_shape');continue
        oracle=q.adjudicate(vals)
        if not oracle['legal']:unknown.append(rev+':illegal_source')
        if rev=='after' and oracle['failures']:unknown.append('fixed_oracle_violation')
        if any(f['obligation']!='keep_mask' for f in oracle['failures']):unknown.append(rev+':unqualified_failure')
        labels={a['label']:a for a in candidate};triggers=set();failures=q.positions(n['failures'])
        try:
            for t in n['triggers']:
                cycle=int(re.fullmatch(r'cycle=(\d+)',t['detail'])[1]);a=labels[t['id']]
                due=cycle+(a['timing']=='next_sample')
                if due<len(vals) and not vals[due]['rst']:triggers.add(due)
            for f in n['failures']:
                if f['id'] not in labels:raise ValueError('unknown_label')
        except Exception:unknown.append(rev+':unknown_marker')
        data[rev]=dict(trace=vals,oracle=oracle,failed=sorted(failures),effective_triggers=sorted(triggers))
    if len(data)==2:
        keys=('rst','sv','sd','sk','sl','mr')
        if any(any(a[k]!=b[k] for k in keys) for a,b in zip(data['before']['trace'],data['after']['trace'])):unknown.append('different_actual_inputs')
    if unknown or len(data)!=2:
        return dict(ordinary=False,history=False,unknown=unknown or ['missing_trace'],lost=[],new_false=[],evidence=data)
    a,b=data['before'],data['after'];failed=set(a['failed']);triggers=set(a['effective_triggers']);targets={c['cycle'] for c in a['oracle']['failures']}
    public={c for c in targets if scenarios[a['trace'][c]['sid']]['scope']=='public'};history=targets-public
    if not public or not history:unknown.append('no_required_target_exposure')
    false_before=failed-targets;false_after=set(b['failed']);fp=false_before|false_after
    O=not(unknown or public-failed or public-triggers or fp)
    H=O and not(history-failed or history-triggers)
    return dict(ordinary=O,history=H,unknown=unknown,lost=sorted(set(protected)-failed),
        new_false=sorted(fp),public_targets=sorted(public),history_targets=sorted(history),
        public_missed=sorted(public-failed),history_missed=sorted(history-failed),
        public_untriggered=sorted(public-triggers),history_untriggered=sorted(history-triggers),
        false_before=sorted(false_before),false_after=sorted(false_after),evidence=data)


def evaluate(candidate,out,scenarios):
    for rev in ('before','after'):
        q.old.native.run_native(q.bench(candidate,scenarios),out/rev,extra_sources=[P/'rtl'/rev/'axis_adapter.v'])


def feedback_request(first,candidate,ev):
    req=copy.deepcopy(first);body=json.loads(req['messages'][1]['content']);body['current_assertions']=candidate
    body['current_status']='Rejected by historical policy; original partial baseline remains active. Repair this proposal using actual history feedback.'
    a,b=ev['evidence']['before'],ev['evidence']['after']
    ids=sorted(set(ev['lost']+ev['history_missed']+ev['new_false']))[:10]
    body['historical_feedback']=dict(lost_baseline_count=len(ev['lost']),history_missed_count=len(ev['history_missed']),
        false_positive_count=len(ev['new_false']),unknown=ev['unknown'],samples=[dict(cycle=c,
        before=a['trace'][max(0,c-1):c+2],after=b['trace'][max(0,c-1):c+2],
        independent_checks=[f for f in a['oracle']['checks'] if f['cycle']==c],
        candidate_failed=c in a['failed'],candidate_triggered=c in a['effective_triggers']) for c in ids])
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'));req['seed']=16508
    return req


def timing_key(d):
    return (tuple(d['frames']),d['gap'],tuple(int(t>=2 and t>=d['ready_delay'] and t%d['stall_period']!=0) for t in range(96)),d['keep'],d['reset_at'])


def pools(prep):
    protocol=q.read(prep/'protocol.json');dev=q.read(P/'scenarios.json');used={timing_key(d) for d in dev};result={}
    for name,c in protocol['future_independent']['strata'].items():
        canonical={}
        for length,gap,delay,period in itertools.product(c['lengths'],c['gap'],range(c['ready_delay'][0],c['ready_delay'][1]+1),c['stall_period']):
            d=dict(frames=[length],gap=gap,ready_delay=delay,stall_period=period,reset_at=-1,keep=c['keep'],scope='history' if name=='historical_target' else 'public',stratum=name)
            key=timing_key(d)
            if key not in used:canonical.setdefault(key,d)
        result[name]=list(canonical.values())
    return result


def actual_signatures(trace):
    groups={}
    for v in trace:groups.setdefault(v['sid'],[]).append(v)
    result=[]
    for values in groups.values():
        end=max(i for i,v in enumerate(values) if v['rst'] or v['sv'] or v['mv'])
        # Ignore payload and irrelevant ready toggles while no output is valid.
        signature=[(v['rst'],v['sv'],v['sr'] if v['sv'] else 0,v['sl'] if v['sv'] else 0,v['sk'] if v['sv'] else 0,
                    v['mv'],v['mr'] if v['mv'] else 0,v['ml'] if v['mv'] else 0) for v in values[:end+1]]
        result.append(digest(signature))
    return result


def independent(prep,out,candidate,freeze):
    if not (out/'terminal_freeze.json').is_file() or digest(candidate)!=freeze['H']:raise ValueError('not_frozen')
    rng=random.Random(16509);selected=[];available=pools(prep)
    for name,required in [('current_target',8),('historical_target',8),('legal_control',16)]:
        if len(available[name])<required:raise ValueError('insufficient_fresh_capacity')
        chosen=rng.sample(available[name],required)
        offset=len(selected)
        selected.extend(dict(d,id=offset+i) for i,d in enumerate(chosen))
    q.dump(out/'independent/scenarios.json',selected)
    q.dump(out/'independent/input_freeze.json',dict(candidate_hash=digest(candidate),scenarios_hash=digest(selected),created=time.time()))
    evaluate(candidate,out/'independent/native',selected)
    ev=measure(candidate,out/'independent/native',selected)
    novelty=True;exposure=True
    if len(ev['evidence'])==2:
        # Never draw replacements after observing actual traces.
        sig=actual_signatures(ev['evidence']['after']['trace'])
        oldsig=actual_signatures(q.old.trace(N/'baseline/after'))
        for root in ('research159_history_native_20261028_r01','research160_history_native_20261028_r01'):
            vals=q.old.trace(q.ROOT/'deliverables'/root/'axis_adapter_keep/p32/after')
            for v in vals:v['sid']=v['cycle']//40
            oldsig.extend(actual_signatures(vals))
        novelty=len(set(sig))==len(sig) and not(set(sig)&set(oldsig))
        targets=set(ev.get('public_targets',[])+ev.get('history_targets',[]))
        counts={d['id']:sum(ev['evidence']['before']['trace'][c]['sid']==d['id'] for c in targets) for d in selected}
        exposure=all(counts[d['id']]>0 if d['keep']==0 else counts[d['id']]==0 for d in selected)
        q.dump(out/'independent/actual_novelty.json',dict(new_signatures=sig,prior_signatures=oldsig,passed=novelty,targets_per_scenario=counts))
    else:novelty=exposure=False
    passed=ev['history'] and novelty and exposure and not ev['unknown']
    q.dump(out/'independent/evaluation.json',ev)
    result=dict(passed=passed,actual_novelty=novelty,all_required_scenarios_exposed=exposure,unknown=ev['unknown'],scenarios=len(selected),candidate_unchanged=digest(candidate)==freeze['H'],rerolls=0)
    q.dump(out/'independent/result.json',result);return result


class RealBackend:
    mode='real'
    def __init__(self,prep,out):self.model=Model(out/'service',q.read(prep/'model_config.json'))
    def generate(self,req,path,current):
        self.model.pending_request=req
        return self.model.call(path,current,'adapter_keep_protection',{},'prospective_history')
    def native(self,candidate,path,scenarios):evaluate(candidate,path,scenarios);return path
    def independent(self,prep,out,candidate,freeze):return independent(prep,out,candidate,freeze)


def costs(out,mode):
    attempts=list(out.rglob('attempt.json')) if mode=='real' else []
    calls=[q.read(p.parent/'transport_result.json') if (p.parent/'transport_result.json').exists() else {} for p in attempts]
    compiles=[q.read(p) for p in out.rglob('compile.json')];execs=[q.read(p) for p in out.rglob('execute.json')]
    return dict(model_calls=len(calls),prompt_tokens=sum(x['prompt_tokens'] for x in calls) if all(x.get('prompt_tokens') is not None for x in calls) else None,
        completion_tokens=sum(x['completion_tokens'] for x in calls) if all(x.get('completion_tokens') is not None for x in calls) else None,
        native_compiles=len(compiles),native_executions=len(execs),compile_seconds=sum(x['wall_seconds'] for x in compiles),execute_seconds=sum(x['wall_seconds'] for x in execs),formal_calls=0)


def execute(prep,out,backend):
    out.mkdir(parents=True,exist_ok=False);budget=Budget();initial=q.read(prep/'initial.json');scenarios=q.read(P/'scenarios.json')
    protected=q.read(prep/'protected.json');first_req=q.read(prep/'request.preview.json')
    active={'O':initial,'H':initial};first=None;state='not_started';recovered=False;tests=None
    q.dump(out/'execution_mode.json',dict(mode=backend.mode,local_test_not_model=backend.mode!='real'))
    def dispatch(path,req,current,permission=None):
        budget.reserve_call(path,req,permission);budget.save(out)
        call,c=backend.generate(req,out/path/'model_call',current);ev=None
        if c is not None:
            adapt(dict(assertions=c,reason='validation_only'))
            if signature(c) in (signature(initial),signature(current)):
                q.dump(out/path/'repeat_rejected.json',dict(reason='Same executable expressions, including reordered/renamed proposals.'));c=None
            else:
                budget.reserve_native(path);budget.save(out)
                source=backend.native(c,out/path/'native',scenarios)
                ev=measure(c,source,scenarios,protected)
                q.dump(out/path/'evaluation.json',ev)
        return call,c,ev
    try:
        call,c,ev=dispatch('shared',first_req,initial)
        o=bool(ev and ev['ordinary']);h=bool(ev and ev['history'])
        state=branch(call['status'],ev is not None,o,h,len(ev['lost']) if ev else 0,len(ev['new_false']) if ev else 0,len(ev['unknown']) if ev else 0)
        first=dict(ordinary=o,history=h,branch=state,measured=ev is not None)
        if o:active['O']=c
        if h:active['H']=c
        q.dump(out/'shared_decision.json',dict(**first,active_hashes={k:digest(v) for k,v in active.items()},baseline_hash=digest(initial),
            retained_historical_detection_ids=protected if not h else None))
        if state=='history_once':
            req=feedback_request(first_req,c,ev);q.dump(out/'recovery/request.preview.json',req)
            call,c2,ev2=dispatch('recovery',req,c,state)
            recovered=bool(ev2 and ev2['history'] and not ev2['unknown'])
            if recovered:active['H']=c2
            state='full_recovery_accepted' if recovered else 'stop_recovery_failed'
        q.dump(out/'terminal_versions.json',active)
        if recovered:
            freeze={k:digest(v) for k,v in active.items()}
            q.dump(out/'terminal_freeze.json',dict(**freeze,rtl={r:q.sha(P/'rtl'/r/'axis_adapter.v') for r in ('before','after')},time=time.time(),local_test=backend.mode!='real'))
            budget.reserve_native('independent',True);budget.save(out)
            tests=backend.independent(prep,out,active['H'],freeze)
            state='independent_pass' if tests.get('passed') else 'stop_independent_failed' if backend.mode=='real' else 'local_fixture_gate_only'
    except Exception as exc:
        state='stop_exception';q.dump(out/'exception.json',dict(type=type(exc).__name__,retries=0))
        raise
    finally:
        budget.save(out);q.dump(out/'cost.json',costs(out,backend.mode))
        q.dump(out/'outcome.json',dict(mode=backend.mode,status=state,first=first,full_recovery_accepted=recovered,
            independent=tests,real_chain_success=bool(backend.mode=='real' and recovered and tests and tests.get('passed')),
            conditional_recovery_denominator=int(backend.mode=='real' and first is not None and first['branch']=='history_once'),
            conditional_recovery_numerator=int(backend.mode=='real' and recovered),automatic_expansion=False))


class FixtureBackend:
    mode='local_state_machine_test_not_model'
    def __init__(self,names):self.names=iter(names);self.used=[];self.current=None;self.independent_called=False
    def generate(self,req,path,current):
        name=next(self.names);self.used.append(name);self.current=name
        if name=='transport':return dict(status='transport_timeout'),None
        if name=='interface':return dict(status='response_received'),None
        return dict(status='response_received'),q.read(P/'controls'/f'{name}.json')['assertions']
    def native(self,candidate,path,scenarios):return N/self.current
    def independent(self,prep,out,candidate,freeze):
        assert (out/'terminal_freeze.json').is_file() and digest(candidate)==freeze['H']
        self.independent_called=True
        return dict(passed=False,status='local_gate_spy_only_no_independent_inputs_generated')


def local_checks(prep,out):
    checks=[]
    def check(name,value):checks.append(dict(check=name,passed=bool(value)));assert value,name
    req=q.read(prep/'request.preview.json');cases=[(['replacement','complementary'],True,True),(['complementary'],False,False),
        (['overbroad'],False,False),(['baseline'],False,False),(['transport'],False,False),(['interface'],False,False),(['replacement','replacement'],True,False)]
    for i,(names,opportunity,recovery) in enumerate(cases):
        b=FixtureBackend(names);path=out/f'local_case_{i}';execute(prep,path,b);r=q.read(path/'outcome.json')
        check(str(names)+' branch',(r['first']['branch']=='history_once')==opportunity)
        check(str(names)+' recovery',r['full_recovery_accepted']==recovery)
        check(str(names)+' independent gate only after recovery',b.independent_called==recovery)
        check(str(names)+' no real cost',q.read(path/'cost.json')['model_calls']==0 and not r['real_chain_success'])
        if opportunity:check(str(names)+' original retained after first rejection',q.read(path/'shared_decision.json')['active_hashes']['H']==digest(q.read(prep/'initial.json')))
    # Existing branch function exhaustively tested, including critical unknown.
    for status,measured,o,h,lost,fp,unknown in itertools.product(('response_received','timeout'),(False,True),(False,True),(False,True),(0,1),(0,1),(0,1)):
        expected=status=='response_received' and measured and o and not h and bool(lost or fp) and not unknown
        check('branch '+str((status,measured,o,h,lost,fp,unknown)),(branch(status,measured,o,h,lost,fp,unknown)=='history_once')==expected)
    def rejects(name,fn):
        try:fn()
        except (ValueError,AssertionError):checks.append(dict(check=name,passed=True))
        else:raise AssertionError(name)
    valid=dict(assertions=q.read(prep/'initial.json'),reason='local interface check')
    check('interface preserves expressions',adapt(valid)==valid['assertions'])
    repeated=copy.deepcopy(valid);repeated['assertions'].append(dict(repeated['assertions'][0],label='second_nonfinal'))
    check('multiple properties per obligation permitted',len(adapt(repeated))==4)
    for name,edit in [('missing reason',lambda v:v.pop('reason')),('reserved label',lambda v:v['assertions'][0].update(label='final')),
                      ('duplicate label',lambda v:v['assertions'][1].update(label=v['assertions'][0]['label'])),
                      ('foreign signal',lambda v:v['assertions'][0].update(antecedent='secret_internal')),
                      ('unsupported timing',lambda v:v['assertions'][0].update(timing='eventually'))]:
        bad=copy.deepcopy(valid);edit(bad);rejects(name,lambda:adapt(bad))
    reordered=copy.deepcopy(valid['assertions'][::-1])
    for i,a in enumerate(reordered):a['label']='renamed'+str(i)
    check('reordering and renaming rejected as duplicate',signature(reordered)==signature(valid['assertions']))
    interrupted=out/'cost_fixture';q.dump(interrupted/'attempt.json',dict(status='local_test_not_submitted'))
    interrupted_cost=costs(interrupted,'real')
    check('interrupted attempt retains count and unknown usage',interrupted_cost['model_calls']==1 and interrupted_cost['prompt_tokens'] is None and interrupted_cost['completion_tokens'] is None)
    grant=dict(purpose=PURPOSE,authorized_calls=2,endpoint=transport.DEFAULT_URL,model='deepseek/deepseek-v3-0324',prepared_sha256='local-fixture',run_output='local-output')
    validate_grant(grant,'local-fixture','local-output')
    check('grant matching scope accepted locally',True)
    for field,value in [('purpose','old'),('authorized_calls',3),('authorized_calls',True),('endpoint','https://other.invalid'),('model','other'),('prepared_sha256','old'),('run_output','other')]:
        bad=dict(grant);bad[field]=value;rejects('grant binding '+field,lambda:validate_grant(bad,'local-fixture','local-output'))
    req2=copy.deepcopy(req);req2['seed']+=1
    b=Budget();b.reserve_call('shared',req);b.reserve_native('shared');b.reserve_call('recovery',req2,'history_once');b.reserve_native('recovery');b.reserve_native('independent',True)
    rejects('third model call',lambda:b.reserve_call('recovery',req2,'history_once'))
    rejects('independent replay twice',lambda:b.reserve_native('independent',True))
    rejects('independent before recovery',lambda:Budget().reserve_native('independent',True))
    huge=copy.deepcopy(req);huge['messages']=[dict(role='user',content='x'*60000)]
    rejects('request reservation cap',lambda:Budget().reserve_call('shared',huge))
    for stop in ('stop_transport','stop_unknown','stop_ordinary_rejects','stop_both_accept_no_discrimination'):
        b=Budget();b.reserve_call('shared',req);rejects('recovery forbidden '+stop,lambda:b.reserve_call('recovery',req2,stop))
    for field,value in [('model','other'),('seed',1),('temperature',1),('max_tokens',2048)]:
        bad=copy.deepcopy(req);bad[field]=value;rejects('immutable '+field,lambda:Budget().reserve_call('shared',bad))
    now=[0];b=Budget(clock=lambda:now[0]);now[0]=1200;rejects('wall limit',lambda:b.reserve_call('shared',req))
    for name in ('baseline','replacement','complementary','overbroad'):
        a=q.read(P/'controls'/f'{name}.json')['assertions'];m=measure(a,N/name,q.read(P/'scenarios.json'),q.read(prep/'protected.json'))
        orig=next(r for r in q.read(R/'qualification/acceptance_matrix.json') if r['control']==name)
        check('unchanged native gates '+name,m['ordinary']==orig['ordinary'] and m['history']==orig['history'] and m['lost']==orig['lost_prior_detections'])
    check('same first request',req==q.read(R/'qualification/pilot/request.preview.json'))
    capacity={k:len(v) for k,v in pools(prep).items()}
    check('capacity rechecked without drawing tests',capacity=={'current_target':48,'historical_target':288,'legal_control':336})
    check('no independent scenarios generated during local tests',not list(out.rglob('scenarios.json')))
    q.dump(out/'checks.json',checks);q.dump(out/'capacity.json',capacity)
    return checks


def verify(prep):
    for name,h in q.read(prep/'seal.json').items():assert q.sha(prep/name)==h,name
    for name,h in q.read(prep/'code_bindings.json').items():assert q.sha(q.ROOT/name)==h,name
    q.verify(P)


def prepare(out):
    q.verify(P)
    for n,h in q.read(R/'seal.json').items():assert q.sha(R/n)==h,n
    out.mkdir(parents=True,exist_ok=False)
    for name in ('protocol.json','request.preview.json'):q.dump(out/name,q.read(R/'qualification/pilot'/name))
    q.dump(out/'initial.json',q.read(P/'controls/baseline.json')['assertions'])
    q.dump(out/'protected.json',q.read(R/'qualification/retained_baseline.json')['retained_native_detections'])
    q.dump(out/'model_config.json',dict(remote_url=transport.DEFAULT_URL,remote_model='deepseek/deepseek-v3-0324',max_model_calls=2,max_tokens=120000,max_wall_seconds=1200,call_timeout=300,
        options=dict(seed=16507,temperature=0.2,num_predict=1024)))
    checks=local_checks(out,out/'local_preflight')
    protocol=q.read(out/'protocol.json');protocol.update(status='controller_integrated_local_checked_awaiting_authorization',purpose=PURPOSE,
        time_limit=1200,call_deadline=300,utf8_reservation_limit_per_call=60000,utf8_reservation_limit_total=120000,
        reservations_are_not_actual_tokens=True,
        gates='Frozen development verdicts preserved; same/next implication trigger markers aligned to checking edge. Original ordinary all-property false-positive guard includes all correct samples; only added historical TARGET checks can add rejection here. H/R equivalence unchanged.',
        independent_scope='Only recovered H version tested on32 newly selected shapes; O terminal frozen and retained but no O holdout execution under the sealed2-compile independent cap. No comparative O/H holdout claim.',
        runtime='research167_adapter_controller execute shared across real and explicitly labeled fixture backends; credentials only read after explicit grant verification and dispatch.',
        checks_passed=len(checks))
    q.dump(out/'protocol.json',protocol)
    dependencies=[Path(__file__),Path(q.__file__),Path(q.old.__file__),Path(q.old.native.__file__),Path(transport.__file__),BRANCH_FILE,
        q.ROOT/'scripts/research17_model.py',q.ROOT/'scripts/research20_model.py',R/'seal.json',P/'seal.json',N/'results.json']
    # Bind all actual fixture baselines/logs used by the local gate; never provider credentials.
    dependencies += [f for f in N.rglob('*') if f.is_file() and 'obj_dir' not in f.parts]
    for root in ('research159_history_native_20261028_r01','research160_history_native_20261028_r01'):
        dependencies += list((q.ROOT/'deliverables'/root/'axis_adapter_keep/p32/after').glob('*.log'))
    q.dump(out/'code_bindings.json',{q.old.rel(p):q.sha(p) for p in dependencies})
    (out/'SUMMARY.md').write_text('# axis_adapter 预算控制器本地集成\n\n首轮请求与research166逐字一致；原生目标及历史接受规则复核一致。'+str(len(checks))+'项本地接口/分支/预算检查通过，未调用模型、未新增原生执行、未选择独立场景。\n\n同一执行状态机用明确标注的手写原生日志夹具测试：额外拒绝后恢复入口、两规则同时接受、普通拒绝、重复/重排提案、接口失败和服务失败；unknown拒绝和调用上限另做穷举。局部测试不能计真实恢复。\n\n最多2次：共享提案1次，仅O接受/H拒绝且确认退化无unknown才恢复1次。拒绝保留旧基线；完整恢复后冻结，再生成独立32场景。新独立只执行H版本，保留O冻结版本但不宣称O/H独立测试对比。无重试、不扩种子、不抽替代测试。\n\n未来调用需本用途/封存哈希/输出路径绑定的明确授权。真实条件恢复仍0/0不可估计。\n')
    q.dump(out/'seal.json',{p.relative_to(out).as_posix():q.sha(p) for p in out.rglob('*') if p.is_file()})
    verify(out);print('SEALED167',len(checks),'local checks; model0; native0; independent0',flush=True)


def run(prep,out,authorization):
    verify(prep);g=q.read(authorization)
    assert not out.exists(), 'output_already_exists_no_resume_or_retry'
    validate_grant(g,q.sha(prep/'seal.json'),q.old.rel(out))
    # Construct transport in a separate directory only after validated grant.
    service=out.parent/(out.name+'_transport')
    service.mkdir(parents=True,exist_ok=False)
    backend=RealBackend(prep,service)
    try:execute(prep,out,backend)
    finally:
        if out.exists():q.dump(out/'authorization.json',g)
        verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','verify','run'])
    for n in ('prepared','out','authorization'):ap.add_argument('--'+n,type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED167; no remote calls')
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
