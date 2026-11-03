"""Original frame_len bounded controller; prepare/check never submit model calls.

Reuses the sealed branch and budget policy, the native runner, and research178
transaction reconstruction. Local handwritten fixtures are never model results.
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
import sys
import time
from types import SimpleNamespace
import research178_partial_qualification as q

ROOT=q.ROOT;read=q.s.read;dump=q.dump;sha=q.s.sha;rel=q.s.rel
P178=ROOT/'deliverables/research178_partial_prepare_20261029_r01'
N178=ROOT/'deliverables/research178_partial_run_20261029_r01'
R178=ROOT/'deliverables/research178_partial_report_20261029_r01'
PURPOSE='research179_original_frame_len_history_pilot'
ENDPOINT='https://api.highwayapi.ai/openai/chat/completions'
MODEL='deepseek/deepseek-v3-0324'
SIGNALS={'rst','monitor_axis_tvalid','monitor_axis_tready','monitor_axis_tlast','monitor_axis_tkeep',
         'frame_len','frame_len_valid','acc_bytes','beat_bytes','prev_complete','accept','finish'}
OBLIGATIONS={'per_frame_length','completion_valid'}
LEGACY=ROOT/'scripts/research167_adapter_controller.py'
BRANCH=ROOT/'scripts/research136_prospective_history.py'
VALIDATOR=ROOT/'scripts/research165_adapter_qualification.py'


def load_functions(path,names,namespace):
    nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert len(nodes)==len(names)
    tree=ast.Module(body=nodes,type_ignores=[]);ast.fix_missing_locations(tree)
    exec(compile(tree,str(path),'exec'),namespace)


# Only selected pure functions/classes are imported. No provider or credentials
# are instantiated by local preparation. Original files remain byte-identical.
load_functions(VALIDATOR,{'validate'},globals())
load_functions(BRANCH,{'branch'},globals())
_legacy=dict(time=time,json=json,hashlib=hashlib,re=re,copy=copy,
             q=sys.modules[__name__],PURPOSE=PURPOSE,transport=SimpleNamespace(DEFAULT_URL=ENDPOINT))
load_functions(LEGACY,{'digest','signature','adapt','validate_grant','Budget','costs'},_legacy)
digest=_legacy['digest'];signature=_legacy['signature'];adapt=_legacy['adapt']
validate_grant=_legacy['validate_grant'];costs=_legacy['costs']


class Budget(_legacy['Budget']):
    def save(self,out):
        dump(out/'budget_ledger.json',dict(reserved_calls=self.calls,native_stages=self.native,
            compiles_reserved=4*len(self.native),note='Two configurations x original before/after; UTF8 reservation is not measured token usage.'))


def controls():
    def p(label,ant,con,ob):return dict(label=label,antecedent=ant,consequent=con,timing='next_sample',obligations=[ob])
    v=p('valid_check',"1'b1",'frame_len_valid == $past(finish)','completion_valid')
    a=p('adjacent_length','finish && prev_complete','frame_len_valid && frame_len == $past(acc_bytes+beat_bytes)','per_frame_length')
    b=dict(a,label='separated_length',antecedent='finish && !prev_complete')
    full=dict(a,label='all_length',antecedent='finish')
    broad=dict(full,label='single_beat_length',consequent='frame_len_valid && frame_len == $past(beat_bytes)')
    never=dict(full,label='never_length',antecedent='finish && acc_bytes<0')
    return dict(baseline=[v,a],replacement=[v,b],union=[v,a,b],full=[v,full],overbroad=[v,broad],vacuous=[v,never])


def bench(candidate,cfg,rows):
    adapt(dict(assertions=candidate,reason='frontend validation'))
    text=q.bench(cfg,rows);start=text.index('adjacent_length:');end=text.index('initial begin')
    props=[]
    for a in candidate:
        op='|=>' if a['timing']=='next_sample' else '|->'
        props.extend([f'{a["label"]}: assert property (@(posedge clk) disable iff(rst) ({a["antecedent"]}) {op} ({a["consequent"]})) else $display("ASSERT_FAIL {a["label"]} cycle=%0d",$sampled(cycle));',
            f'always @(posedge clk) if(!rst && ({a["antecedent"]})) $display("TRIGGER {a["label"]} cycle=%0d",cycle);'])
    return text[:start]+'\n'.join(props)+'\n'+text[end:]


def evaluate(candidate,out,rows):
    for cfg in (0,1):
        cfg_rows=rows[cfg] if isinstance(rows,dict) else rows
        for rev in ('before','after'):
            r=q.s.n.run_native(bench(candidate,cfg,cfg_rows),out/str(cfg)/rev,
                extra_sources=[q.PREV/'frame_len_consecutive'/rev/'axis_frame_len.v'])
            if r['compile_status']!='passed' or r['execution_status']!='completed':return


def evidence_key(cfg,cycle,ob):return f'{cfg}:{cycle}:{ob}'


def measure(candidate,folder,rows,protected=(),fixture_subset=False):
    """Native alarms are matched to their OWN mapped obligations and triggers."""
    labels={a['label']:a for a in adapt(dict(assertions=candidate,reason='validate'))}
    unknown=[];data={};detected=set();public=set();history=set();false=[];effective=set();mapping=[]
    for cfg in (0,1):
        cfg_rows=rows[cfg] if isinstance(rows,dict) else rows
        for rev in ('before','after'):
            path=folder/str(cfg)/rev
            if not (path/'result.json').exists():unknown.append(f'{cfg}/{rev}:missing_native');continue
            n=read(path/'result.json');tr=q.s.trace(path)
            if n['compile_status']!='passed' or n['execution_status']!='completed':unknown.append(f'{cfg}/{rev}:incomplete_native');continue
            if len(tr)!=len(cfg_rows) or any(v['cycle']!=i for i,v in enumerate(tr)):unknown.append(f'{cfg}/{rev}:trace_shape');continue
            actual=[[v[k] for k in ('rst','v','r','k','last')] for v in tr]
            expected=[[v['rst'],v['v'],v['r'],v['k'] if cfg else 1,v['last']] for v in cfg_rows]
            if actual!=expected:unknown.append(f'{cfg}/{rev}:stimulus_mismatch');continue
            try:frames,cancel=q.independent_events(tr,cfg)
            except (AssertionError,KeyError):unknown.append(f'{cfg}/{rev}:reference_or_source_invalid');continue
            refs={};exp=q.s.frame_expected(tr,cfg)
            for i,(v,e) in enumerate(zip(tr,exp)):
                refs[i]={'completion_valid':None if v['rst'] else ('pass' if v['valid']==e['valid'] else 'violation'),
                         'per_frame_length':None if v['rst'] or not e['valid'] else ('pass' if v['valid'] and v['length']==e['length'] else 'violation')}
            targets={f['check_cycle']:f for f in frames if f['status']=='violation'}
            if any(f['status']=='unknown' for f in frames):unknown.append(f'{cfg}/{rev}:unknown_response')
            if rev=='after' and any('violation' in x.values() for x in refs.values()):unknown.append(f'{cfg}/fixed_reference_failure')
            if rev=='before':
                for cy,f in targets.items():(history if f['context']=='adjacent' else public).add(evidence_key(cfg,cy,'per_frame_length'))
            try:
                triggers=q.marker_map(n,'triggers');alarms=q.marker_map(n,'failures')
                if not fixture_subset and any(label not in labels for label,cy in triggers|alarms):raise ValueError('foreign_marker')
                own=set()
                for label,cy in triggers:
                    if label not in labels:continue
                    due=cy+(labels[label]['timing']=='next_sample')
                    if due>=len(tr):
                        # Terminal vacuity of an unconditional diagnostic is not a
                        # pending transaction; actual completion has padding.
                        if tr[cy]['v'] and tr[cy]['r'] and tr[cy]['last']:unknown.append(f'{cfg}/{rev}:truncated_obligation')
                        continue
                    if tr[cy]['rst'] or tr[due]['rst']:continue
                    own.add((label,due))
                    if rev=='before':
                        for ob in labels[label]['obligations']:
                            if refs[due][ob] is not None:effective.add(evidence_key(cfg,due,ob))
                alarms_out=[]
                for label,cy in alarms:
                    if label not in labels:continue
                    obs=labels[label]['obligations'];states=[refs.get(cy,{}).get(ob) for ob in obs]
                    if (label,cy) not in own or any(x is None for x in states):
                        unknown.append(f'{cfg}/{rev}/{label}/{cy}:unresolved_alarm');verdict='unknown'
                    elif 'violation' in states:
                        verdict='target_detection'
                        for ob,state in zip(obs,states):
                            if state=='violation' and rev=='before':detected.add(evidence_key(cfg,cy,ob))
                    else:verdict='false_positive';false.append(f'{cfg}/{rev}/{label}/{cy}')
                    alarms_out.append(dict(label=label,cycle=cy,obligations=obs,verdict=verdict))
                mapping.extend(dict(config=cfg,revision=rev,label=a['label'],obligations=a['obligations'],
                    trigger_cycles=sorted(cy for lab,cy in own if lab==a['label']),
                    alarms=[x for x in alarms_out if x['label']==a['label']]) for a in candidate)
                data[f'{cfg}/{rev}']=dict(trace=tr,frames=frames,cancelled=cancel,alarms=alarms_out)
            except (ValueError,KeyError,TypeError):unknown.append(f'{cfg}/{rev}:invalid_native_markers')
    if len(data)!=4:unknown.append('missing_configuration_or_revision')
    if not public or not history:unknown.append('no_required_class_exposure')
    O=not(unknown or false or public-detected or public-effective)
    H=O and not(history-detected or history-effective or set(protected)-detected)
    return dict(ordinary=bool(O),history=bool(H),unknown=unknown,lost=sorted(set(protected)-detected),new_false=false,
        public_targets=sorted(public),history_targets=sorted(history),detected=sorted(detected),
        public_missed=sorted(public-detected),history_missed=sorted(history-detected),
        public_untriggered=sorted(public-effective),history_untriggered=sorted(history-effective),mapping=mapping,evidence=data)


def scenario(d):
    """Future generator definition only; selection is gated by recovery freeze."""
    rows=[]
    def add(rst=0,v=0,r=1,k=15,last=0):rows.append(dict(cycle=len(rows),rst=rst,v=v,r=r,k=k,last=last))
    def frame(length,stall=0):
        for i in range(length):
            k=d['tail'] if i==length-1 else 15
            if i==0:
                for _ in range(stall):add(v=1,r=0,k=k,last=int(length==1))
            add(v=1,k=k,last=int(i==length-1))
    add(rst=1);add(rst=1);frame(d['prefix'],d['prefix_stall'])
    for _ in range(d['gap']):add()
    if d['stratum']=='reset':
        add(v=1,last=0);add(v=1,r=0,last=0);add(rst=1);add(rst=1);frame(2,1)
    else:frame(2 if d['stratum']=='legal' else 1,d['boundary_stall'])
    for _ in range(5):add()
    return rows


def semantic_key(rows,cfg):
    return digest([(v['rst'],v['v'],v['r'] if v['v'] else 0,(v['k'] if cfg else 1) if v['v'] else 0,v['last'] if v['v'] else 0) for v in rows])


def pools():
    used={semantic_key(read(q.PREV/'frame_stimuli.json'),cfg) for cfg in (0,1)};result={}
    for cfg in (0,1):
        for name in ('historical','current','legal','reset'):
            pool={}
            for length,tail,ps,gap,bs in itertools.product((4,5,6,7),(1,3,7,15) if cfg else (1,),(1,2),(0,) if name=='historical' else (2,3,4),(0,) if name=='historical' else (1,2)):
                d=dict(config=cfg,stratum=name,prefix=length,tail=tail,prefix_stall=ps,gap=gap,boundary_stall=bs)
                key=semantic_key(scenario(d),cfg)
                if key not in used:pool.setdefault(key,d)
            result[f'{cfg}/{name}']=list(pool.values())
    return result


def feedback_request(first,candidate,ev):
    req=copy.deepcopy(first);body=json.loads(req['messages'][1]['content'])
    body['current_assertions']=candidate;body['status']='History rejected this proposal; partial baseline remains active. Restore lost protection while retaining current targets.'
    samples=[]
    for key in ev['lost'][:8]:
        cfg,cy,ob=key.split(':');cy=int(cy)
        samples.append(dict(obligation=ob,config=int(cfg),before=ev['evidence'][cfg+'/before']['trace'][max(0,cy-1):cy+1],
            after=ev['evidence'][cfg+'/after']['trace'][max(0,cy-1):cy+1]))
    body['history_feedback']=dict(lost=len(ev['lost']),false_alarms=ev['new_false'],unknown=ev['unknown'],actual_samples=samples)
    req['messages'][1]['content']=json.dumps(body,ensure_ascii=False);req['seed']=16508
    return req


def independent(prep,out,candidate,freeze):
    assert (out/'terminal_freeze.json').exists() and digest(candidate)==freeze['H']
    rng=random.Random(17909);rows=[];chosen=[];segments=[]
    for group,pool in pools().items():
        for d in rng.sample(pool,4):
            seq=scenario(d);start=len(rows);rows.extend(dict(v,cycle=start+i) for i,v in enumerate(seq))
            chosen.append(d);segments.append(dict(start=start,end=len(rows),descriptor=d))
    # Each chosen scenario is tested only in its assigned configuration. Run
    # both configurations in four native jobs using separate concatenated input.
    outi=out/'independent';dump(outi/'selected.json',chosen);checks=[];evs=[]
    for cfg in (0,1):
        cr=[];ranges=[]
        for d in chosen:
            if d['config']!=cfg:continue
            seq=scenario(d);start=len(cr);cr.extend(dict(v,cycle=start+i) for i,v in enumerate(seq));ranges.append((start,len(cr),d))
        dump(outi/f'inputs_{cfg}.json',cr)
        for rev in ('before','after'):
            q.s.n.run_native(bench(candidate,cfg,cr),outi/'native'/str(cfg)/rev,
                extra_sources=[q.PREV/'frame_len_consecutive'/rev/'axis_frame_len.v'])
        evs.append((cfg,cr,ranges))
    # The same gate supports different per-configuration inputs by a local
    # adapter below; all scenarios must actually expose their declared class.
    ev=measure_variable(candidate,outi/'native',{cfg:cr for cfg,cr,rs in evs},[])
    for cfg,cr,ranges in evs:
        frames=ev.get('evidence',{}).get(f'{cfg}/before',{}).get('frames',[])
        for start,end,d in ranges:
            f=[f for f in frames if start<=f['anchor_cycle']<end and f['status']=='violation']
            exposed=any(x['context']==('adjacent' if d['stratum']=='historical' else 'separated') for x in f) if d['stratum'] in ('historical','current') else not f
            checks.append(dict(descriptor=d,exposed=exposed,semantic_hash=semantic_key(scenario(d),cfg)))
    passed=ev['history'] and all(x['exposed'] for x in checks) and len({(x['descriptor']['config'],x['semantic_hash']) for x in checks})==32
    result=dict(passed=passed,scenarios=32,exposure=checks,unknown=ev['unknown'],rerolls=0,scope='Recovered H only; finite original frame_len simulation')
    dump(outi/'evaluation.json',ev);dump(outi/'result.json',result);return result


def measure_variable(candidate,folder,rows_by_cfg,protected):
    # RowsForConfig is selected only at the cfg iteration; ordinary development
    # uses the same list for both. Keep a single authoritative verdict routine.
    return measure(candidate,folder,rows_by_cfg,protected)


def execute(prep,out,backend):
    out.mkdir(parents=True,exist_ok=False);budget=Budget();initial=read(prep/'initial.json');rows=read(prep/'development.json')
    protected=read(prep/'protected.json');req=read(prep/'request.preview.json');active={'O':initial,'H':initial}
    first=None;recovered=False;tests=None;state='not_started'
    dump(out/'execution_mode.json',dict(mode=backend.mode,local_test_not_model=backend.mode!='real'))
    def dispatch(stage,request,current,permission=None):
        budget.reserve_call(stage,request,permission);budget.save(out)
        call,c=backend.generate(request,out/stage/'model_call',current);ev=None
        if c is not None:
            adapt(dict(assertions=c,reason='runtime validation'))
            if signature(c) in (signature(initial),signature(current)):
                dump(out/stage/'repeat_rejected.json',dict(reason='Repeated/renamed/reordered expressions'));c=None
            else:
                budget.reserve_native(stage);budget.save(out)
                folder=backend.native(c,out/stage/'native',rows)
                ev=measure(c,folder,rows,protected,fixture_subset=backend.mode!='real')
                dump(out/stage/'evaluation.json',ev)
        return call,c,ev
    try:
        call,c,ev=dispatch('shared',req,initial)
        o=bool(ev and ev['ordinary']);h=bool(ev and ev['history'])
        state=branch(call['status'],ev is not None,o,h,len(ev['lost']) if ev else 0,len(ev['new_false']) if ev else 0,len(ev['unknown']) if ev else 0)
        first=dict(ordinary=o,history=h,branch=state)
        if o:active['O']=c
        if h:active['H']=c
        dump(out/'shared_decision.json',dict(**first,active_hashes={k:digest(v) for k,v in active.items()},retained_old_detection_ids=protected if not h else None))
        if state=='history_once':
            req2=feedback_request(req,c,ev);dump(out/'recovery/request.preview.json',req2)
            call,c2,ev2=dispatch('recovery',req2,c,state)
            recovered=bool(ev2 and ev2['history'] and not ev2['unknown'])
            if recovered:active['H']=c2
            state='full_recovery_accepted' if recovered else 'stop_recovery_failed'
        dump(out/'terminal_versions.json',active)
        if recovered:
            freeze={k:digest(v) for k,v in active.items()};freeze.update(rtl={r:sha(q.PREV/'frame_len_consecutive'/r/'axis_frame_len.v') for r in ('before','after')},local_test=backend.mode!='real',created=time.time())
            dump(out/'terminal_freeze.json',freeze);budget.reserve_native('independent',True);budget.save(out)
            tests=backend.independent(prep,out,active['H'],freeze)
            state=('independent_pass' if tests['passed'] else 'stop_independent_failed') if backend.mode=='real' else 'local_fixture_gate_only'
    except Exception as exc:
        state='stop_exception';dump(out/'exception.json',dict(type=type(exc).__name__,retries=0));raise
    finally:
        budget.save(out);dump(out/'cost.json',costs(out,backend.mode))
        dump(out/'outcome.json',dict(status=state,mode=backend.mode,first=first,full_recovery_accepted=recovered,independent=tests,
            real_chain_success=bool(backend.mode=='real' and recovered and tests and tests['passed']),
            conditional_recovery_denominator=int(backend.mode=='real' and first is not None and first['branch']=='history_once'),
            conditional_recovery_numerator=int(backend.mode=='real' and recovered),automatic_expansion=False))


class FixtureBackend:
    mode='local_fixture_not_model'
    def __init__(self,names):self.names=iter(names);self.independent_called=False
    def generate(self,req,path,current):
        name=next(self.names)
        if name in ('transport','interface'):return dict(status='transport_timeout' if name=='transport' else 'response_received'),None
        return dict(status='response_received'),controls()[name]
    def native(self,candidate,path,rows):return N178
    def independent(self,prep,out,candidate,freeze):
        assert digest(candidate)==freeze['H'] and (out/'terminal_freeze.json').exists()
        self.independent_called=True;return dict(passed=False,status='spy_only_no_holdout_selected_or_executed')


def verify(prep):
    for k,h in read(prep/'seal.json').items():assert sha(prep/k)==h,k
    for k,h in read(prep/'code_bindings.json').items():assert sha(ROOT/k)==h,k
    q.verify(P178)


def run(prep,out,authorization):
    verify(prep);grant=read(authorization);validate_grant(grant,sha(prep/'seal.json'),rel(out))
    assert not out.exists(),'no_resume_or_retry'
    # Remote transport import and credentials access are inaccessible to prepare.
    import research69_deadline_transport as transport
    class Model(transport.RemoteModel):
        def _payload(self,*args):return self.pending_request
        def save_decoded_output(self,folder,value,current,secret):
            candidate=adapt(value);dump(folder/'candidate.json',candidate);return candidate,'expressions_preserved'
    class RealBackend:
        mode='real'
        def __init__(self):self.model=Model(out.parent/(out.name+'_transport'),read(prep/'model_config.json'))
        def generate(self,request,path,current):
            self.model.pending_request=request;return self.model.call(path,current,'per_frame_length',{},'prospective_history')
        def native(self,candidate,path,rows):evaluate(candidate,path,rows);return path
        def independent(self,*args):return independent(*args)
    try:execute(prep,out,RealBackend())
    finally:
        if out.exists():dump(out/'authorization.json',grant)
        verify(prep)


def local_checks(prep,out):
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)));dump(out/'checks.json',checks);assert value,name
    def rejects(name,fn):
        try:fn()
        except (AssertionError,ValueError,TypeError,KeyError):check(name,True)
        else:check(name,False)
    rows=read(prep/'development.json');req=read(prep/'request.preview.json');protected=read(prep/'protected.json')
    matrix=[]
    old={r['candidate']:r for r in read(R178/'all_control_decisions.json')}
    for name,cand in controls().items():
        ev=measure(cand,N178,rows,protected,True)
        key={'baseline':'partial_adjacent','replacement':'replacement_separated','union':'union','full':'full_length','overbroad':'overbroad_single_beat','vacuous':'vacuous'}[name]
        check('unchanged qualification O/H '+name,(ev['ordinary'],ev['history'])==(old[key]['ordinary_accept'],old[key]['history_accept']))
        check('known complete references '+name,not ev['unknown'])
        check('old/current counts '+name,len(ev['history_targets'])==6 and len(ev['public_targets'])==2)
        dump(out/'fixture_evidence'/f'{name}.json',ev)
        matrix.append(dict(control=name,ordinary=ev['ordinary'],history=ev['history'],lost=ev['lost'],false=ev['new_false'],unknown=ev['unknown']))
    dump(out/'fixture_matrix.json',matrix)
    for index,(names,opportunity,recovery) in enumerate([
        (['replacement','union'],True,True),(['union'],False,False),(['overbroad'],False,False),
        (['vacuous'],False,False),(['baseline'],False,False),(['transport'],False,False),
        (['interface'],False,False),(['replacement','replacement'],True,False),(['replacement','overbroad'],True,False)]):
        backend=FixtureBackend(names);folder=out/f'branch_{index}';execute(prep,folder,backend);result=read(folder/'outcome.json')
        check(str(names)+' branch',(result['first']['branch']=='history_once')==opportunity)
        check(str(names)+' recovery',result['full_recovery_accepted']==recovery)
        check(str(names)+' holdout spy only',backend.independent_called==recovery)
        check(str(names)+' not real recovery',not result['real_chain_success'] and result['conditional_recovery_denominator']==0 and read(folder/'cost.json')['model_calls']==0)
        if opportunity:check(str(names)+' H retains baseline',read(folder/'shared_decision.json')['active_hashes']['H']==digest(read(prep/'initial.json')))
    for status,measured,o,h,lost,fp,unknown in itertools.product(('response_received','timeout'),(False,True),(False,True),(False,True),(0,1),(0,1),(0,1)):
        expected=status=='response_received' and measured and o and not h and bool(lost or fp) and not unknown
        check('branch '+str((status,measured,o,h,lost,fp,unknown)),(branch(status,measured,o,h,lost,fp,unknown)=='history_once')==expected)
    c=controls()['union'];check('multiple assertions same obligation',adapt(dict(assertions=c,reason='test'))==c)
    for name,fn in [('missing reason',lambda v:v.pop('reason')),('reserved label',lambda v:v['assertions'][0].update(label='initial')),
                    ('duplicate label',lambda v:v['assertions'][1].update(label=v['assertions'][0]['label'])),
                    ('private signal',lambda v:v['assertions'][0].update(antecedent='dut.frame_len_reg == 0')),
                    ('cycle whitelist',lambda v:v['assertions'][0].update(antecedent='cycle == 17')),
                    ('missing mapping',lambda v:v['assertions'][0].update(obligations=[])),
                    ('unknown obligation',lambda v:v['assertions'][0].update(obligations=['other'])),
                    ('unsupported timing',lambda v:v['assertions'][0].update(timing='eventually'))]:
        v=copy.deepcopy(dict(assertions=c,reason='test'));fn(v);rejects(name,lambda:adapt(v))
    renamed=[dict(a,label='new'+str(i)) for i,a in enumerate(reversed(c))]
    check('renamed/reordered repeat',signature(renamed)==signature(c))
    wrong=[dict(a,obligations=['completion_valid']) for a in c]
    m=measure(wrong,N178,rows,protected,True)
    check('cannot borrow another obligation violation',not m['ordinary'] and bool(m['new_false']) and len(m['public_missed'])==2)
    badrows=copy.deepcopy(rows);badrows[3]['k']=7
    m=measure(c,N178,badrows,protected,True);check('input mismatch is unknown rejection',not m['ordinary'] and bool(m['unknown']))
    check('different per-config input API',measure_variable(c,N178,{0:rows,1:rows},protected)['unknown']!=[]) # foreign control labels correctly rejected
    req2=copy.deepcopy(req);req2['seed']=16508
    b=Budget();b.reserve_call('shared',req);b.reserve_native('shared');b.reserve_call('recovery',req2,'history_once');b.reserve_native('recovery');b.reserve_native('independent',True)
    rejects('third call',lambda:b.reserve_call('recovery',req2,'history_once'))
    rejects('second independent run',lambda:b.reserve_native('independent',True))
    rejects('holdout before recovery',lambda:Budget().reserve_native('independent',True))
    for state in ('stop_unknown','stop_transport','stop_ordinary_rejects','stop_both_accept_no_discrimination'):
        bb=Budget();bb.reserve_call('shared',req);rejects('forbidden recovery '+state,lambda:bb.reserve_call('recovery',req2,state))
    for field,val in [('model','other'),('seed',0),('temperature',1),('max_tokens',2048)]:
        r=copy.deepcopy(req);r[field]=val;rejects('fixed sampling '+field,lambda:Budget().reserve_call('shared',r))
    huge=copy.deepcopy(req);huge['messages']=[dict(role='user',content='x'*60000)];rejects('reservation cap',lambda:Budget().reserve_call('shared',huge))
    clock=[0];bb=Budget(clock=lambda:clock[0]);clock[0]=1200;rejects('wall deadline',lambda:bb.reserve_call('shared',req))
    grant=dict(purpose=PURPOSE,authorized_calls=2,endpoint=ENDPOINT,model=MODEL,prepared_sha256='test',run_output='local')
    validate_grant(grant,'test','local');check('grant positive',True)
    for field,val in [('purpose','old'),('authorized_calls',3),('authorized_calls',True),('prepared_sha256','old'),('run_output','other'),('endpoint','other'),('model','other')]:
        g=dict(grant);g[field]=val;rejects('grant '+field,lambda:validate_grant(g,'test','local'))
    capacity={k:len(v) for k,v in pools().items()}
    check('all eight strata have >=4 unused shapes',len(capacity)==8 and all(v>=4 for v in capacity.values()))
    for group,pool in pools().items():
        cfg=int(group[0]);check('canonical dedup '+group,len({semantic_key(scenario(d),cfg) for d in pool})==len(pool))
        check('new prefix length '+group,all(d['prefix']>3 for d in pool))
    dump(out/'capacity.json',dict(available=capacity,required_per_stratum=4,planned_total=32,selection_performed=False,
        method='Canonical legal input shapes, ignoring inactive KEEP/ready values. New completed prefix length4..7 exceeds all research177/178 completed frames (max3). No original output or test verdict used.',
        limitation='Capacity is not actual target exposure or independent success; both must be checked after frozen-version execution.'))
    # A fresh invocation of the new frontend must run on the originals; fixtures
    # alone cannot certify compilation or parameter binding of this interface.
    evaluate(c,out/'new_interface_native',rows)
    m=measure(c,out/'new_interface_native',rows,protected)
    check('new frontend native full protection',m['history'] and not m['unknown'] and not m['new_false'])
    check('new frontend old/current targets',len(m['history_targets'])==6 and len(m['public_targets'])==2)
    check('variable input adapter native compatibility',measure_variable(c,out/'new_interface_native',{0:rows,1:rows},protected)['history'])
    dump(out/'new_interface_evaluation.json',m)
    check('no independent inputs selected',not list(out.rglob('selected.json')))
    check('no provider attempts',not list(out.rglob('attempt.json')))
    return checks


def prepare(out):
    q.verify(P178)
    for directory in (R178,N178):
        for key,h in read(directory/'seal.json').items():assert sha(directory/key)==h,key
    out.mkdir(parents=True,exist_ok=False);rows=read(q.PREV/'frame_stimuli.json');initial=controls()['baseline']
    base=measure(initial,N178,rows,fixture_subset=True)
    assert not base['unknown'] and len(base['detected'])==6 and len(base['public_missed'])==2
    dump(out/'initial.json',initial);dump(out/'development.json',rows);dump(out/'protected.json',base['detected'])
    source=[r for r in read(q.PREV/'source_manifest.json') if r['case']=='frame_len_consecutive']
    dump(out/'rtl_versions.json',source)
    public_samples=[]
    for cfg in (0,1):
        frames=base['evidence'][f'{cfg}/before']['frames']
        for f in frames:
            if f['context']!='separated':continue
            cy=f['check_cycle']
            public_samples.append(dict(config=cfg,accepted=f['accepted'],obligation='per_frame_length',expected_length=f['expected_length'],
                before=base['evidence'][f'{cfg}/before']['trace'][cy-1:cy+1],after=base['evidence'][f'{cfg}/after']['trace'][cy-1:cy+1]))
    body=dict(task='Revise or complement this editable partial SVA set for original axis_frame_len. Return the entire set; no fixed protective assertion is injected.',
        specification=read(q.PREV/'contracts.json')['frame_len'],
        interface=dict(signals=sorted(SIGNALS),obligations=sorted(OBLIGATIONS),timing=['same_sample','next_sample'],
            monitor='acc_bytes is bytes in unfinished accepted frame before this edge; beat_bytes is current beat byte count; finish=valid&&ready&&last; prev_complete means the previous clock accepted last. All monitor assignments are passive and reset to0. Properties sample pre-edge; registered output for accepted TLAST is checked next edge. No cycle/sid/internal RTL identifiers allowed.',
            parameters='Both configurations: DATA_WIDTH8 KEEP_ENABLE0 KEEP_WIDTH1; DATA_WIDTH32 KEEP_ENABLE1 KEEP_WIDTH4; LEN_WIDTH16. Contiguous low KEEP masks, bounded no overflow.'),
        rtl={r['revision']:(ROOT/r['path']).read_text() for r in source},current_assertions=initial,public_development=public_samples,
        output_schema=dict(assertions=[dict(label='unique_nonreserved_identifier',antecedent='SystemVerilog Boolean expression',consequent='SystemVerilog Boolean expression',timing='same_sample or next_sample',obligations=['per_frame_length or completion_valid'])],reason='explain changes'),
        acceptance='Native compilation/execution and independent input-event reference. Current separated targets, applicable legal false alarms and effective triggers checked. Preserve prior functional protection. Unknown does not pass. No manually repaired predicates. Up to6 properties, multiple per obligation allowed.')
    req=dict(model=MODEL,seed=16507,temperature=0.2,max_tokens=1024,messages=[dict(role='system',content='Generate SystemVerilog concurrent assertions as strict JSON only. Use only the declared interface. Preserve expressions exactly in the response.'),dict(role='user',content=json.dumps(body,ensure_ascii=False))])
    dump(out/'request.preview.json',req)
    dump(out/'model_config.json',dict(remote_url=ENDPOINT,remote_model=MODEL,max_model_calls=2,max_tokens=120000,max_wall_seconds=1200,call_timeout=300,options=dict(seed=16507,temperature=0.2,num_predict=1024)))
    dump(out/'protocol.json',dict(purpose=PURPOSE,status='local_integration_in_progress',authorization='none; separate explicit purpose/seal/output-bound grant required',
        generation='Existing DeepSeek transport; full editable set representation; initial handwritten research178 partial control explicitly disclosed. No success controls sent.',
        shared_calls=1,conditional_recovery_calls=1,max_calls=2,retries=0,time_limit_seconds=1200,call_timeout_seconds=300,
        utf8_reservation_per_call=60000,utf8_reservation_total=120000,reservations_are_actual_tokens=False,
        max_native_compiles=12,max_native_executions=12,
        branch='One shared proposal. Oaccept/Hreject plus confirmed lost protection or new false alarm and zero critical unknown => one history-feedback recovery. Otherwise stop. Repeated/renamed/reordered candidates stop before compilation.',
        ordinary='All exposed separated frame targets detected and effectively triggered; all mapped applicable reference-pass samples guarded; incomplete, unresolved alarms and fixed-reference failures reject.',
        historical='Identical O guard plus adjacent historical targets and previously protected evidence retained with effective triggers. H/R equivalent. No unique R benefit claim.',
        public_history_split='Actual accepted input completion adjacency, no sample-ID/value/cycle whitelist. Same reference, full native execution and false-positive guard for both rules.',
        freeze='Only complete recovery accepts H and freezes versions/RTL hashes before fresh local tests; no recovery opportunity => no independent run in this protocol.',
        future_independent=dict(planned_scenarios=32,configs=[0,1],per_config=dict(historical=4,current=4,legal=4,reset=4),seed=17909,
            execution='Recovered H only; no O versus H independent-test comparison',stop='All selected inputs retained, no rerolls or response-driven changes. No required exposure => fail. Failure used for editing converts entire batch to development.'),
        exclusions='research174/175 and all prior independent results not read for selection, rules, prompts or tests. research177/178 observations are development, not novel search discoveries.',
        limitations='Same original frame-length carryover defect, two temporal contexts. Structural fixtures do not show real generation/recovery or cross-case stability.'))
    checks=local_checks(out,out/'local_preflight')
    # Save all development inputs, source and implementation bindings; credentials
    # and any independent samples are deliberately absent.
    deps=[Path(__file__),LEGACY,BRANCH,VALIDATOR,Path(q.__file__),Path(q.s.__file__),Path(q.s.n.__file__),
        ROOT/'scripts/research69_deadline_transport.py',ROOT/'scripts/research20_model.py',ROOT/'scripts/research17_model.py',
        P178/'seal.json',R178/'seal.json',N178/'seal.json']
    deps.extend(ROOT/r['path'] for r in source)
    for cfg in (0,1):
        for rev in ('before','after'):
            deps.extend(N178/str(cfg)/rev/f for f in ('result.json','execute.log','tb.sv'))
    dump(out/'code_bindings.json',{rel(p):sha(p) for p in deps})
    dump(out/'development_exclusions.json',dict(source_experiment='research177 + research178',stimulus_sha256=digest(rows),
        configs=[0,1],accepted_frame_lengths=sorted({len(f['accepted']) for f in base['evidence']['0/before']['frames']}),
        known_targets=base['public_targets']+base['history_targets'],all_local_fixture_data_is_development=True,
        no_claim_about_deleted_or_external_records=True))
    protocol=read(out/'protocol.json');protocol.update(status='sealed_local_verified_awaiting_separate_authorization',checks_passed=len(checks));dump(out/'protocol.json',protocol)
    cost=costs(out,'local');dump(out/'local_cost.json',cost)
    summary=f'''# research179 frame_len 控制器本地集成与封存

已完成本地集成及{len(checks)}项检查，未调用模型、未抽取或执行新独立测试。封存首轮请求仅待未来明确授权，本轮不申请调用。

复用research167预算规则和research136分支，接入原始frame_len RTL、可编辑多性质映射、原生编译/执行及按自身义务归因的接受检查。research178的旧目标6个、当前目标2个仍保持相同本地决定：部分基线保护6/6且遗漏2/2；替换对照普通接受、历史拒绝；联合对照全部通过。新的接口在两种配置、原始前后RTL上实际编译执行4次，旧/新目标全部检出，无合法误报和关键unknown。它仍是手写正对照，不是模型恢复。

本地状态机验证了额外拒绝、保留旧版本、恢复成功/失败、重复提案、普通拒绝、两组同时接受、接口/传输失败及unknown阻断；恢复后的独立入口只调用测试探针，未生成测试。多个性质可映射同一义务；其他义务的报警不能借用长度错误作为检出。

未来协议最多2次：共享新提案1次；仅普通接受、历史拒绝且确认退化、无关键unknown时恢复1次。无机会就停，无重试、不扩种子。完整恢复后冻结，仅对恢复的H版本生成32个新场景；两配置分别覆盖相邻目标、间隔目标、合法多拍及复位取消。无曝光或独立失败均保留，不补抽。

独立容量按规范化输入时序枚举，未选择样本。新完成前缀长度4至7拍，开发材料最大为3拍；无效周期的KEEP/ready变化不计新样本。容量见local_preflight/capacity.json；这不等于已验证实际曝光或独立通过。

请求含原始前后RTL、规格、初始部分性质及公共开发采样；不含手写完整/替换对照、历史答案清单或独立数据。新增请求的采样与既有生成流程一致，公共生成能力不计作机制收益。所有新本地材料均为开发数据。

真实模型调用0，条件恢复仍0/0不可估计；H/R等价及576次搜索负结果不变。旧源码、旧实验封存及失败均未修改。

只读复核：
```powershell
wsl -- python3 scripts/research179_frame_controller.py verify --prepared {rel(out)}
```

重新本地集成检查需新输出目录：
```powershell
wsl -- python3 scripts/research179_frame_controller.py prepare --out deliverables/research179_frame_recheck
```
'''
    (out/'SUMMARY.md').write_text(summary,encoding='utf-8');q.seal(out);verify(out)
    print('SEALED179',len(checks),'checks; native4 model0 independent0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','verify','run'])
    for name in ('prepared','out','authorization'):ap.add_argument('--'+name,type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED179 no model calls')
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
