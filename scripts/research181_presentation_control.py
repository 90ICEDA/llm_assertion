"""Lossless sampling-presentation capability pilot. Local prepare makes no calls.

No mechanism-effect claim: both arms share the full historical acceptance gate.
Only their rendering of exactly the same permitted sample facts differs.
"""
import argparse
import copy
import itertools
import json
from pathlib import Path
import time
import research179_frame_controller as c

ROOT=c.ROOT;P=ROOT/'deliverables/research179_frame_controller_prepare_20261029_r01'
R=ROOT/'deliverables/research179_frame_controller_run_20261029_r01'
D=ROOT/'deliverables/research180_frame_failure_diagnosis_20261029_r01'
PURPOSE='research181_frame_sampling_presentation_capability_control'
ARMS=('C','T')
ALIASES=dict(cycle='sample_cycle',rst='rst',v='monitor_axis_tvalid',r='monitor_axis_tready',
             k='monitor_axis_tkeep',last='monitor_axis_tlast',length='frame_len',valid='frame_len_valid',
             acc='acc_bytes',prev='prev_complete')
SOURCE_FIELDS=list(ALIASES)
META=['record','config','obligation','expected_length']
ACCEPT=['record','accept_order','accept_cycle','accepted_bytes']
SAMPLES=['record','revision','sampling_position']+list(ALIASES.values())


def encode(records,arm):
    if arm=='C':return copy.deepcopy(records)
    if arm!='T':raise ValueError('unknown_arm')
    result=dict(layout='explicit_anchor_check_tables_v1',frame_columns=META,frames=[],accepted_columns=ACCEPT,accepted=[],sample_columns=SAMPLES,samples=[])
    for i,rec in enumerate(records):
        if set(rec)!={'config','obligation','expected_length','accepted','before','after'}:raise ValueError('sample_fields')
        result['frames'].append([i,rec['config'],rec['obligation'],rec['expected_length']])
        for j,beat in enumerate(rec['accepted']):
            if set(beat)!={'cycle','bytes'}:raise ValueError('accepted_fields')
            result['accepted'].append([i,j,beat['cycle'],beat['bytes']])
        for rev in ('before','after'):
            if len(rec[rev])!=2:raise ValueError('two_samples_required')
            for j,row in enumerate(rec[rev]):
                if set(row)!=set(SOURCE_FIELDS):raise ValueError('trace_fields')
                result['samples'].append([i,rev,'anchor' if j==0 else 'check']+[row[k] for k in SOURCE_FIELDS])
    return result


def decode(value,arm):
    if arm=='C':return copy.deepcopy(value)
    if arm!='T' or value.get('layout')!='explicit_anchor_check_tables_v1':raise ValueError('layout')
    if value['frame_columns']!=META or value['accepted_columns']!=ACCEPT or value['sample_columns']!=SAMPLES:raise ValueError('columns')
    result=[]
    for i,row in enumerate(value['frames']):
        if len(row)!=4 or row[0]!=i:raise ValueError('frame_order')
        result.append(dict(config=row[1],obligation=row[2],expected_length=row[3],accepted=[],before=[],after=[]))
    for row in value['accepted']:
        if len(row)!=4:raise ValueError('accepted_row')
        i,j,cy,n=row
        if j!=len(result[i]['accepted']):raise ValueError('accept_order')
        result[i]['accepted'].append(dict(cycle=cy,bytes=n))
    for row in value['samples']:
        if len(row)!=3+len(SOURCE_FIELDS):raise ValueError('sample_row')
        i,rev,pos=row[:3]
        if rev not in ('before','after') or pos!=('anchor' if not result[i][rev] else 'check') or len(result[i][rev])>=2:raise ValueError('sample_order')
        result[i][rev].append(dict(zip(SOURCE_FIELDS,row[3:])))
    if encode(result,'T')!=value:raise ValueError('noncanonical_or_missing_samples')
    return result


def normalize(request,arm):
    req=copy.deepcopy(request);body=json.loads(req['messages'][1]['content'])
    body['public_development']=decode(body['public_development'],arm)
    if 'own_feedback' in body:
        body['own_feedback']['samples']=decode(body['own_feedback']['samples'],arm)
    req['messages'][1]['content']=body
    return req


def request_for(body,arm,round_index):
    req=copy.deepcopy(c.read(P/'request.preview.json'));req['seed']=16507+round_index
    body=copy.deepcopy(body);body['public_development']=encode(body['public_development'],arm)
    if 'own_feedback' in body:body['own_feedback']['samples']=encode(body['own_feedback']['samples'],arm)
    req['messages'][1]['content']=json.dumps(body,ensure_ascii=False)
    return req


def refinement_request(first,arm,candidate,ev):
    body=normalize(first,arm)['messages'][1]['content']
    body['current_assertions']=candidate
    body['status']='This arm failed full native acceptance. Revise using only its actual development diagnostics; preserve prior detections and remove legal false alarms.'
    samples=[]
    for cfg in (0,1):
        a=ev['evidence'][f'{cfg}/before'];b=ev['evidence'][f'{cfg}/after']
        for f in a['frames']:
            cy=f['check_cycle']
            samples.append(dict(config=cfg,obligation='per_frame_length',expected_length=f['expected_length'],accepted=f['accepted'],
                before=a['trace'][cy-1:cy+1],after=b['trace'][cy-1:cy+1]))
    body['own_feedback']=dict(samples=samples,ordinary=ev['ordinary'],full_history=ev['history'],
        public_missed=ev['public_missed'],history_missed=ev['history_missed'],false_alarms=sorted(ev['new_false']),
        lost=ev['lost'],unknown=ev['unknown'],public_untriggered=ev['public_untriggered'],history_untriggered=ev['history_untriggered'])
    return request_for(body,arm,1)


def decide(status,candidate_present,repeated,ev,round_index):
    if status!='response_received':return 'global_stop_transport'
    if not candidate_present:return 'stop_interface'
    if repeated:return 'stop_repeat'
    if ev is None or ev['unknown']:return 'stop_unknown'
    if ev['history']:return 'accept'
    return 'refine_once' if round_index==0 else 'stop_budget_rejected'


class Budget:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.start=clock();self.entries=[];self.native=[];self.arm_start={}
    def reserve_call(self,arm,round_index,request,permission=None):
        if arm not in ARMS:raise ValueError('arm')
        now=self.clock();self.arm_start.setdefault(arm,now)
        if now-self.start>=2400 or now-self.arm_start[arm]>=1200:raise ValueError('wall_limit')
        previous=[r for r in self.entries if r['arm']==arm]
        if len(self.entries)>=4 or len(previous)>=2 or round_index!=len(previous):raise ValueError('call_limit_or_order')
        if round_index and permission!='refine_once':raise ValueError('refinement_permission')
        if (request['model'],request['seed'],request['temperature'],request['max_tokens'])!=(c.MODEL,16507+round_index,0.2,1024):raise ValueError('fixed_sampling')
        reserve=sum(len(m['content'].encode()) for m in request['messages'])+2048+1024
        if reserve>60000 or sum(x['reservation'] for x in previous)+reserve>120000:raise ValueError('byte_reservation_limit')
        self.entries.append(dict(arm=arm,round=round_index,request_hash=c.digest(request),reservation=reserve))
    def reserve_native(self,arm,stage,all_frozen=False,accepted=False):
        key=[arm,stage]
        if arm not in ARMS or key in self.native or len(self.native)>=6:raise ValueError('native_cap_or_repeat')
        if stage=='independent':
            if not all_frozen or not accepted:raise ValueError('holdout_before_terminal_accept')
        elif stage not in ('r0','r1') or not self.entries or (self.entries[-1]['arm'],self.entries[-1]['round'])!=(arm,int(stage[1])):raise ValueError('native_before_call')
        self.native.append(key)
    def save(self,out):c.dump(out/'budget_ledger.json',dict(calls=self.entries,native_stages=self.native,native_compiles_reserved=4*len(self.native),byte_reservation_not_actual_tokens=True))


def execute(prep,out,backend):
    out.mkdir(parents=True,exist_ok=False);budget=Budget();initial=c.read(prep/'initial.json');rows=c.read(prep/'development.json');protected=c.read(prep/'protected.json')
    terminal={};stop_global=False;tests={}
    c.dump(out/'execution_mode.json',dict(mode=backend.mode,local_fixture=backend.mode!='real'))
    try:
        for arm in ARMS:
            if stop_global:
                terminal[arm]=dict(status='not_run_global_stop',accepted=False,candidate=initial);continue
            first=c.read(prep/arm/'request.preview.json');req=first;current=initial;seen={c.signature(initial)};permission=None
            for round_index in range(2):
                stage=f'r{round_index}';path=out/'arms'/arm/stage
                budget.reserve_call(arm,round_index,req,permission);budget.save(out)
                call,candidate=backend.generate(arm,req,path/'model_call',current);ev=None;repeated=False
                if candidate is not None:
                    c.adapt(dict(assertions=candidate,reason='validate'))
                    repeated=c.signature(candidate) in seen
                    if not repeated:
                        seen.add(c.signature(candidate));budget.reserve_native(arm,stage);budget.save(out)
                        folder=backend.native(candidate,path/'native',rows)
                        ev=c.measure(candidate,folder,rows,protected,fixture_subset=backend.mode!='real')
                        c.dump(path/'evaluation.json',ev)
                decision=decide(call['status'],candidate is not None,repeated,ev,round_index)
                c.dump(path/'decision.json',dict(action=decision,mode=backend.mode,candidate_hash=c.digest(candidate) if candidate is not None else None))
                if decision=='refine_once':
                    current=candidate;req=refinement_request(first,arm,candidate,ev);permission=decision
                    c.dump(out/'arms'/arm/'r1/request.preview.json',req);continue
                terminal[arm]=dict(status=decision,accepted=decision=='accept',candidate=candidate if decision=='accept' else initial,
                    rejected_candidate_hash=c.digest(candidate) if candidate is not None and decision!='accept' else None)
                stop_global=decision=='global_stop_transport';break
        # Freeze every terminal before any test draw. No test result can affect
        # the other arm's generation, selection or terminal version.
        c.dump(out/'terminal_versions.json',terminal)
        frozen={a:c.digest(v['candidate']) for a,v in terminal.items()}
        c.dump(out/'all_terminal_frozen.json',dict(hashes=frozen,accepted={a:v['accepted'] for a,v in terminal.items()},
            rtl=c.read(prep/'rtl_versions.json'),time=time.time(),mode=backend.mode))
        if not stop_global:
            for arm in ARMS:
                if not terminal[arm]['accepted']:continue
                folder=out/'arms'/arm;freeze=dict(H=frozen[arm],all_terminal_freeze=c.sha(out/'all_terminal_frozen.json'),mode=backend.mode)
                c.dump(folder/'terminal_freeze.json',freeze);budget.reserve_native(arm,'independent',True,True);budget.save(out)
                tests[arm]=backend.independent(prep,folder,terminal[arm]['candidate'],freeze)
        c.dump(out/'outcome.json',dict(mode=backend.mode,terminal={a:dict(status=v['status'],accepted=v['accepted']) for a,v in terminal.items()},
            new_real_accepted_versions=sum(v['accepted'] for v in terminal.values()) if backend.mode=='real' else 0,
            independent=tests,global_transport_stop=stop_global,automatic_expansion=False,
            inference='Public generation capability comparison only, not anti-regression or search increment.'))
    except Exception as exc:
        c.dump(out/'exception.json',dict(type=type(exc).__name__,stop='global_no_retry'));raise
    finally:budget.save(out);c.dump(out/'cost.json',c.costs(out,backend.mode))


class FixtureBackend:
    mode='local_fixture_not_model'
    def __init__(self,plans):self.plans={k:iter(v) for k,v in plans.items()};self.calls=[];self.tests=[]
    def generate(self,arm,req,path,current):
        name=next(self.plans[arm]);self.calls.append((arm,name))
        if name in ('transport','interface'):return dict(status='transport_timeout' if name=='transport' else 'response_received'),None
        return dict(status='response_received'),c.controls()[name]
    def native(self,candidate,path,rows):return c.N178
    def independent(self,prep,out,candidate,freeze):
        assert (out.parent.parent/'all_terminal_frozen.json').exists() and c.digest(candidate)==freeze['H']
        self.tests.append(out.name);return dict(passed=False,status='gate_spy_only_no_test_generated')


def validate_grant(g,seal,out):
    if g.get('purpose')!=PURPOSE or type(g.get('authorized_calls')) is not int or g['authorized_calls']!=4:raise ValueError('purpose_budget')
    if g.get('endpoint')!=c.ENDPOINT or g.get('model')!=c.MODEL or g.get('prepared_sha256')!=seal or g.get('run_output')!=out:raise ValueError('grant_binding')


def verify(prep):
    for k,h in c.read(prep/'seal.json').items():assert c.sha(prep/k)==h,k
    for k,h in c.read(prep/'code_bindings.json').items():assert c.sha(ROOT/k)==h,k
    c.verify(P)


def run(prep,out,authorization):
    verify(prep);g=c.read(authorization);validate_grant(g,c.sha(prep/'seal.json'),c.rel(out));assert not out.exists(),'no_resume'
    import research69_deadline_transport as transport
    class Model(transport.RemoteModel):
        def _payload(self,*args):return self.pending_request
        def save_decoded_output(self,folder,value,current,secret):
            cand=c.adapt(value);c.dump(folder/'candidate.json',cand);return cand,'model_expressions_preserved'
    class RealBackend:
        mode='real'
        def __init__(self):self.model=Model(out.parent/(out.name+'_transport'),c.read(prep/'model_config.json'))
        def generate(self,arm,req,path,current):
            self.model.pending_request=req;return self.model.call(path,current,'per_frame_length',{},'presentation_capability')
        def native(self,candidate,path,rows):c.evaluate(candidate,path,rows);return path
        def independent(self,prepared,folder,candidate,freeze):
            result=c.independent(prepared,folder,candidate,freeze)
            result['scope']='Accepted presentation arm '+folder.name+'; finite original frame_len simulation, not historical-recovery treatment'
            c.dump(folder/'independent/result.json',result)
            return result
    try:execute(prep,out,RealBackend())
    finally:
        if out.exists():c.dump(out/'authorization.json',g)
        verify(prep)


def local_checks(prep,out):
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)));c.dump(out/'checks.json',checks);assert value,name
    def rejects(name,fn):
        try:fn()
        except (AssertionError,ValueError,TypeError,KeyError,IndexError):check(name,True)
        else:check(name,False)
    req={arm:c.read(prep/arm/'request.preview.json') for arm in ARMS}
    canonical=normalize(req['C'],'C');records=canonical['messages'][1]['content']['public_development']
    check('same all facts and nonpresentation fields',canonical==normalize(req['T'],'T'))
    check('same ten original public records',records==json.loads(c.read(P/'request.preview.json')['messages'][1]['content'])['public_development'])
    check('both requests different presentation',req['C']!=req['T'])
    for arm in ARMS:
        body=json.loads(req[arm]['messages'][1]['content']);check(arm+' common reset disclosure','disable iff(rst)' in body['interface']['clock_reset_contract'])
        check(arm+' common alias legend',body['interface']['sample_field_aliases']==ALIASES)
        check(arm+' same initial candidate',body['current_assertions']==c.read(P/'initial.json'))
    encoded=encode(records,'T');check('lossless roundtrip',decode(encoded,'T')==records)
    for i,record in enumerate(records):
        for rev in ('before','after'):
            for position in range(2):check(f'sample{i}/{rev}/{position} exact all fields',decode(encoded,'T')[i][rev][position]==record[rev][position])
        check(f'accepted order{i}',decode(encoded,'T')[i]['accepted']==record['accepted'])
    for name,edit in [('wrong column',lambda v:v['sample_columns'].__setitem__(3,'wrong')),
        ('missing sample',lambda v:v['samples'].pop()),('wrong role',lambda v:v['samples'][0].__setitem__(2,'check')),
        ('duplicate accepted order',lambda v:v['accepted'][0].__setitem__(1,5))]:
        bad=copy.deepcopy(encoded);edit(bad);rejects(name,lambda:decode(bad,'T'))
    mutated=copy.deepcopy(encoded);mutated['samples'][0][-1]=42
    check('changed value detectable rather than silently repaired',decode(mutated,'T')!=records)
    rows=c.read(prep/'development.json');protected=c.read(prep/'protected.json')
    # Rejudge every fixed local control; no new simulations or generated proposals.
    controls=[]
    for name,cand in c.controls().items():
        ev=c.measure(cand,c.N178,rows,protected,True)
        old=c.read(P/'local_preflight/fixture_evidence'/f'{name}.json')
        check('unchanged ordinary and historical gate '+name,(ev['ordinary'],ev['history'],ev['unknown'])==(old['ordinary'],old['history'],old['unknown']))
        controls.append(dict(name=name,ordinary=ev['ordinary'],history=ev['history'],false_alarms=len(ev['new_false']),lost=len(ev['lost'])))
        if name=='overbroad':
            feedback={a:refinement_request(req[a],a,cand,ev) for a in ARMS}
            check('same feedback algorithm lossless across arms',normalize(feedback['C'],'C')==normalize(feedback['T'],'T'))
            check('refinement retains all public facts',normalize(feedback['T'],'T')['messages'][1]['content']['public_development']==records)
            own=normalize(feedback['C'],'C')['messages'][1]['content']['own_feedback']
            check('only own actual false alarms',own['false_alarms']==sorted(ev['new_false']))
    c.dump(out/'local_control_decisions.json',controls)
    # Verify actual native render under unchanged imported frontend.
    cand=c.controls()['union'];folder=P/'local_preflight/new_interface_native'
    ev=c.measure(cand,folder,rows,protected)
    check('existing native positive unchanged full accept',ev['history'] and not ev['unknown'])
    for cfg in (0,1):
        for rev in ('before','after'):
            check(f'original frontend exact bytes {cfg}/{rev}',(folder/str(cfg)/rev/'tb.sv').read_text()==c.bench(cand,cfg,rows))
    for status,present,repeat,unknown,accepted,round_index in itertools.product(('response_received','timeout'),(False,True),(False,True),(False,True),(False,True),(0,1)):
        ev=dict(unknown=['test'] if unknown else [],history=accepted)
        action=decide(status,present,repeat,ev,round_index)
        expected=status=='response_received' and present and not repeat and not unknown and not accepted and round_index==0
        check('bounded decision '+str((status,present,repeat,unknown,accepted,round_index)),(action=='refine_once')==expected)
        check('accept only full known '+str((status,present,repeat,unknown,accepted,round_index)),(action=='accept')==(status=='response_received' and present and not repeat and not unknown and accepted))
    scenarios=[({'C':['union'],'T':['union']},2,2),({'C':['overbroad','union'],'T':['replacement','union']},4,2),
        ({'C':['overbroad','overbroad'],'T':['vacuous','replacement']},4,0),({'C':['transport'],'T':[]},1,0),
        ({'C':['interface'],'T':['baseline']},2,0),({'C':['union'],'T':['transport']},2,0)]
    for i,(plan,calls,tests) in enumerate(scenarios):
        backend=FixtureBackend(plan);folder=out/f'controller_{i}';execute(prep,folder,backend);outcome=c.read(folder/'outcome.json')
        check(f'controller{i} bounded calls',len(backend.calls)==calls)
        check(f'controller{i} independent gated after all terminals',len(backend.tests)==tests)
        check(f'controller{i} zero real successes',outcome['new_real_accepted_versions']==0 and c.read(folder/'cost.json')['model_calls']==0)
        if i==2:check('failed correction keeps initial candidate',all(v['candidate']==c.read(prep/'initial.json') for v in c.read(folder/'terminal_versions.json').values()))
    bb=Budget()
    for arm in ARMS:
        bb.reserve_call(arm,0,req[arm]);bb.reserve_native(arm,'r0')
        req2=copy.deepcopy(req[arm]);req2['seed']=16508
        bb.reserve_call(arm,1,req2,'refine_once');bb.reserve_native(arm,'r1')
    bb.reserve_native('C','independent',True,True);bb.reserve_native('T','independent',True,True)
    rejects('global fifth model call',lambda:bb.reserve_call('C',2,req['C'],'refine_once'))
    rejects('repeat independent call',lambda:bb.reserve_native('C','independent',True,True))
    for frozen,accepted in ((False,False),(True,False),(False,True)):
        rejects('holdout gate '+str((frozen,accepted)),lambda:Budget().reserve_native('C','independent',frozen,accepted))
    for field,value in [('model','other'),('seed',1),('temperature',1),('max_tokens',2048)]:
        bad=copy.deepcopy(req['C']);bad[field]=value;rejects('sampling immutable '+field,lambda:Budget().reserve_call('C',0,bad))
    bad=copy.deepcopy(req['C']);bad['messages']=[dict(role='user',content='x'*60000)];rejects('oversized request',lambda:Budget().reserve_call('C',0,bad))
    clock=[0];bb=Budget(clock=lambda:clock[0]);bb.reserve_call('C',0,req['C']);clock[0]=1200
    rejects('arm deadline',lambda:bb.reserve_call('C',1,req['C'],'refine_once'))
    clock[0]=2400;rejects('global deadline',lambda:bb.reserve_call('T',0,req['T']))
    g=dict(purpose=PURPOSE,authorized_calls=4,endpoint=c.ENDPOINT,model=c.MODEL,prepared_sha256='test',run_output='test')
    validate_grant(g,'test','test');check('new-purpose grant positive only local',True)
    for key,value in [('purpose',c.PURPOSE),('authorized_calls',2),('authorized_calls',True),('prepared_sha256','old'),('run_output','elsewhere'),('model','other'),('endpoint','other')]:
        bad=dict(g);bad[key]=value;rejects('grant rejected '+key,lambda:validate_grant(bad,'test','test'))
    check('no new provider attempts',not list(out.rglob('attempt.json')))
    check('no actual independent inputs',not list(out.rglob('selected.json')))
    capacity={k:len(v) for k,v in c.pools().items()};check('unused shape capacity unchanged',capacity==c.read(P/'local_preflight/capacity.json')['available'])
    c.dump(out/'information_equivalence.json',dict(passed=True,canonical_sha256=c.digest(canonical),original_public_records=10,
        accepted_rows=len(encoded['accepted']),sample_rows=len(encoded['samples']),only_differing_body_key='public_development',
        interface_additions_common_to_both=True,first_request_utf8_bytes={a:sum(len(m['content'].encode()) for m in req[a]['messages']) for a in ARMS},
        actual_tokens=None,scope='Proves recoverable facts, not equal model difficulty or attention. Representation length differences are part of treatment and must be costed.'))
    c.dump(out/'capacity.json',dict(available=capacity,required_per_stratum=4,planned_per_accepted_version=32,selected=False))
    return checks


def prepare(out):
    c.verify(P)
    for directory in (D,):
        for key,h in c.read(directory/'seal.json').items():assert c.sha(directory/key)==h,key
    out.mkdir(parents=True,exist_ok=False)
    for name in ('initial.json','development.json','protected.json','rtl_versions.json','development_exclusions.json'):
        c.dump(out/name,c.read(P/name))
    original=c.read(P/'request.preview.json');body=json.loads(original['messages'][1]['content'])
    body['interface']['sample_field_aliases']=ALIASES
    body['interface']['clock_reset_contract']='Every generated assertion is wrapped as @(posedge clk) disable iff(rst). same_sample checks its consequent at the antecedent edge; next_sample checks one clock later. Trace rows are pre-edge samples before nonblocking register updates. Reset cancels active checks; an antecedent requiring rst cannot trigger under this wrapper. Passive acc_bytes/prev_complete also reset to0.'
    body['interface']['record_contract']='For each public record, before and after are original RTL revisions, NOT clock positions. In either revision sample0 is the antecedent anchor edge and sample1 is the following check edge. accepted lists only valid&&ready beats of the completed frame in order. Columns/aliases do not change any values.'
    body['interface']['table_schema']=dict(frame_columns=META,accepted_columns=ACCEPT,sample_columns=SAMPLES,
        note='Both nested and table representations encode the same facts; record and accept_order are presentation indices, forbidden in SVA.')
    for arm in ARMS:c.dump(out/arm/'request.preview.json',request_for(body,arm,0))
    config=c.read(P/'model_config.json');config.update(max_model_calls=4,max_tokens=240000,max_wall_seconds=2400);c.dump(out/'model_config.json',config)
    c.dump(out/'protocol.json',dict(purpose=PURPOSE,status='local_preparation',authorization='none',
        question='Does explicit sampling presentation improve full native acceptance versus the same facts nested? Public generation capability only.',
        treatment='Only public_development and own-feedback sample representation; common alias, clock/reset and record-role explanations identical.',
        arms=dict(C='original nested records',T='lossless explicit frame/accepted-beat/anchor-check tables'),
        model=c.MODEL,seed_per_round=[16507,16508],temperature=0.2,max_output_tokens_per_call=1024,
        budget=dict(max_calls=4,per_arm=2,retries=0,per_call_seconds=300,per_arm_wall_seconds=1200,total_wall_seconds=2400,
                    per_call_utf8_reservation=60000,per_arm_utf8_reservation=120000,max_native_compiles=24,max_native_executions=24),
        execution_order=['C/r0','C/r1 only if known native rejection','T/r0','T/r1 only if known native rejection'],
        refinement='One own-diagnostic refinement after first measured rejection with no critical unknown. Same rule both arms, not conditional O/H recovery; all unaccepted versions preserve the old partial baseline.',
        acceptance='Unchanged research179 measure history gate: current and historical targets, prior detections, own effective triggers, no legal false alarms or critical unknown; same native runner, RTL and configs.',
        stop='Full acceptance stops that arm. Transport failure stops the whole batch. Interface failure, repeated predicates or critical unknown stop that arm. Second rejection stops that arm. No retries, arm budget transfer, reseeding or expansion.',
        terminal='Freeze both terminal decisions/versions before any independent generation. If global transport stop, no independent run. If neither arm accepted, stop this route without independent tests.',
        independent='Only accepted terminal versions use research179 fixed generator and same32 scenarios/config distribution/seed after all terminals freeze. Check actual exposure, false alarms, misses, unknown; no replacement draws or feedback. Initial predicates never selected by tests.',
        reporting='Report both arms including failures, actual calls/tokens/native costs, complete acceptance and independent outcomes. This is a selected-case one-seed capability pilot, not generation stability or either core mechanism benefit.',
        limitations='Lossless facts do not imply equal readability/token cost; report those differences. Common interface corrections prevent attributing comparisons with old research179 to presentation alone.',
        isolation='Only research177/178 development records in initial requests; later own-arm diagnostics only. No research179 failed proposal, full successful control, other-arm outputs or independent data sent. Old failures remain unchanged; old1-call conditional remainder cannot be used.'))
    checks=local_checks(out,out/'local_preflight')
    # Pin the reusable runner/acceptance/transport closure as well as the new renderer.
    deps=dict(c.read(P/'code_bindings.json'))
    for p in (Path(__file__),P/'seal.json',D/'seal.json',R/'outcome.json',R/'budget_ledger.json'):
        deps[c.rel(p)]=c.sha(p)
    c.dump(out/'code_bindings.json',deps)
    prot=c.read(out/'protocol.json');prot.update(status='sealed_locally_checked_not_authorized',checks_passed=len(checks));c.dump(out/'protocol.json',prot)
    c.dump(out/'local_cost.json',dict(model_calls=0,native_compiles=0,native_executions=0,formal_queries=0,independent_runs=0,
        prior_native_pairs_rejudged=4,fixture_decisions_are_not_model_results=True))
    eq=c.read(out/'local_preflight/information_equivalence.json')
    summary=f'''# research181 采样呈现单因素能力对照：本地封存

{len(checks)}项本地检查通过，模型调用0、新增原生执行0、独立测试0。两份真实请求已封存，尚未授权。本轮不申请调用。

两组共同补齐字段别名、@(posedge clk)采样、disable iff(rst)、same/next时序和前后版本/起始检查位置说明。C组保留原嵌套记录；T组将完全相同的记录展成帧信息、接受拍、前后版本的起始/检查采样表。可反向还原全部10条公共记录、{eq['accepted_rows']}条接受拍记录和{eq['sample_rows']}条采样行；其余首轮内容、模型、初始部分候选及采样参数一致。未补入正确替换谓词、完整手写集合或旧模型失败提案。

两组都用未修改的research179原生历史接受检查，既有四次原生执行及六组本地对照的接受决定复核一致。接口和模型谓词不做人工修复。第二轮只使用本组第一轮的实际失败与同一抽取规则，并继续采用本组呈现形式；本地回放证明相同反馈在两种形式下也可无损还原。

未来预算上限4次，每组最多2次：生成一次，只有有完整原生诊断且无关键unknown的拒绝才允许本组一次细化。接受即停；重复、接口失败、关键unknown停止本组；传输失败全批停止。没有完整接受版本就停止该路线，不追加措辞修正、不扩种子，也不挪用research179剩余条件额度。

所有组终态及版本先冻结，再对接受版本执行新的同一批32场景独立测试；本地仅测试入口探针并复核未用语义容量，未选择或运行样本。无曝光或独立失败不得补抽，也不反馈模型。不得把单种子能力先导当作稳定性或两个核心机制收益。

首轮消息UTF8字节：C={eq['first_request_utf8_bytes']['C']}，T={eq['first_request_utf8_bytes']['T']}。信息等价不保证难度/注意力或token成本相等；真实tokens尚不可用，后续必须照实报告成本差异。两组共同新增接口说明，因此旧research179与本实验也不构成纯呈现对照。

当前只是封存准备：新增真实接受0，真实条件恢复仍0/0不可估计，research179拒绝和历史实验保持不变。

只读复核：
```powershell
wsl -- python3 scripts/research181_presentation_control.py verify --prepared {c.rel(out)}
```
重新本地检查（须使用新目录）：
```powershell
wsl -- python3 scripts/research181_presentation_control.py prepare --out deliverables/research181_local_recheck
```
'''
    (out/'SUMMARY.md').write_text(summary,encoding='utf-8');c.q.seal(out);verify(out)
    print('SEALED181',len(checks),'checks; model0 native0 independent0; no authorization',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','verify','run'])
    for name in ('prepared','out','authorization'):ap.add_argument('--'+name,type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED181; local only')
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
