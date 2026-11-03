"""Local-only FIFO interface/controller and unused semantic-space qualification.

No transport import, credentials, model invocation or independent execution.
The injectable controller uses the same branch/budget code as earlier pilots.
Handwritten native controls are NOT generated candidates or model recovery.
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

import research185_drop_partial as q

s=q.s
ROOT=q.ROOT
ARCHIVE=q.D/'research186_drop_monitor_compat_20261102_r01/qualification'
LOCK=q.D/'research182_development_qualification_20261101_r03/public_interface_lock.json'
SIGNALS={'rst','first_present','input_count','input_complete','m_axis_tready','DEPTH'}
OB='oversize_frame_atomic_drop'
FIELDS={'label','antecedent','consequent','timing','obligations'}
PURPOSE='research187_original_sync_fifo_drop_history_pilot'
ENDPOINT='https://api.highwayapi.ai/openai/chat/completions'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def load_pure(path,names,ns):
    tree=ast.parse(path.read_text())
    nodes=[v for v in tree.body if isinstance(v,(ast.FunctionDef,ast.ClassDef)) and v.name in names]
    assert {v.name for v in nodes}==set(names)
    module=ast.Module(body=nodes,type_ignores=[]);ast.fix_missing_locations(module)
    exec(compile(module,str(path),'exec'),ns)


load_pure(ROOT/'scripts/research136_prospective_history.py',{'branch'},globals())
load_pure(ROOT/'scripts/research167_adapter_controller.py',{'Budget','signature'},globals())


def validate(candidate):
    if not isinstance(candidate,list) or not 1<=len(candidate)<=6:raise ValueError('assertion_count')
    labels=set()
    for a in candidate:
        if not isinstance(a,dict) or set(a)!=FIELDS:raise ValueError('fields')
        label=a['label']
        if not isinstance(label,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,39}',label) or label in labels:raise ValueError('label')
        if label in {'module','initial','always','wire','logic','property','assert','begin','end','if','else','final','input','output'}:raise ValueError('reserved_label')
        labels.add(label)
        if a['timing']!='same_sample':raise ValueError('same_sample_first_presentation_scope')
        if a['obligations']!=[OB]:raise ValueError('obligation_mapping')
        for key in ('antecedent','consequent'):
            x=a[key]
            if not isinstance(x,str) or not x or len(x)>1600:raise ValueError('expression')
            t=re.sub(r"\d+'[hHbBdD][0-9a-fA-F_]+",'0',x)
            if set(re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*',t))-SIGNALS:raise ValueError('identifier')
            if re.search(r'[^A-Za-z0-9_\s()&|!~=<>+\-*/%,^]',t) or re.search(r'(?<![=!<>])=(?!=)|//|/\*|\*/|\+\+|--|\|->|\|=>|<<|>>',t):raise ValueError('not_expression')
            if re.search(r'\b[A-Za-z_][A-Za-z0-9_]*\s*\(',t):raise ValueError('function_call')
    return copy.deepcopy(candidate)


def adapt(value):
    if not isinstance(value,dict) or set(value)!={'assertions','reason'} or not isinstance(value['reason'],str):raise ValueError('response_schema')
    return validate(value['assertions'])


def controls():
    props={k:dict(label=k,**v,timing='same_sample',obligations=[OB]) for k,v in q.PROPERTIES.items()}
    return {k:[copy.deepcopy(props[l]) for l in labels] for k,labels in q.CONTROLS.items()}


def bench(candidate,depth,policy,stimulus=None):
    """Reuse sealed monitor, wrapper, stimulus and trace; replace only properties."""
    candidate=validate(candidate)
    text=q.bench(depth,policy)
    lo=text.index('first_stalled: assert property');hi=text.index('initial begin $dumpfile')
    source=''
    for a in candidate:
        source+=f'''{a['label']}: assert property (@(posedge clk) disable iff(rst) ({a['antecedent']}) |-> ({a['consequent']})) else $display("ASSERT_FAIL {a['label']} cycle=%0d",$sampled(cycle));
always @(posedge clk) if(!rst && ({a['antecedent']})) $display("TRIGGER {a['label']} cycle=%0d",cycle);
'''
    text=text[:lo]+source+text[hi:]
    loop='for(j=0;j<256;j=j+1) begin ingress_count[j]<=0;ingress_complete[j]<=0;output_seen[j]<=0;end'
    assert text.count(loop)==1
    text=text.replace(loop,' '.join(f'ingress_count[{j}]<=0;ingress_complete[{j}]<=0;output_seen[{j}]<=0;' for j in range(256)))
    if stimulus is not None:
        # Reuse the exact trace expression; change only the explicit input rows.
        trace=next(line for line in text.splitlines() if line.startswith('@(posedge clk);$display("TRACE'))
        start=text.index('@(negedge clk);cycle=');end=text.index('@(negedge clk);$display("NATIVE_RUN_COMPLETE")')
        driven=''
        for r in stimulus:
            driven+=f"@(negedge clk);cycle={r['cycle']};rst={r['rst']};s_axis_tvalid={r['v']};s_axis_tdata={r['data']};s_axis_tlast={int(r['last'])};s_axis_tid={r['sid']};m_axis_tready={r['ready']};\n{trace}\n"
        text=text[:start]+driven+text[end:]
    return text


def semantic_key(rows,depth):
    """Ignore payload/IDs/cycle origin/idle length; length and drain phase matter."""
    groups={}
    for r in rows:
        if r['v']:groups.setdefault(r['frame'],[]).append(r)
    assert len(groups)==3
    prefix,target,suffix=[groups[k] for k in sorted(groups)]
    gaps=[i for i in range(1,len(target)) if target[i]['cycle']>target[i-1]['cycle']+1]
    assert len(gaps)==1
    tail=target[-1]['cycle']
    post=[r for r in rows if tail<r['cycle']<=tail+12]
    return (depth,len(prefix),len(target),gaps[0],int(all(r['ready'] for r in post)))


def descriptor(depth,policy,excess,gap_offset):
    return dict(depth=depth,policy=policy,excess=excess,gap_offset=gap_offset,
                semantic_key=[depth,depth-1,depth+excess,depth//2+1+gap_offset,int(policy=='ready_first')])


def scene(d):
    depth=d['depth'];values=[]
    def add(rst=0,v=0,data=0,last=0,ready=0,frame=-1):
        values.append(dict(cycle=len(values),rst=rst,v=v,data=data,last=last,ready=ready,frame=frame,sid=frame+1 if v else 0))
    for _ in range(3):add(rst=1)
    for i in range(depth-1):add(v=1,data=1+i,last=i==depth-2,frame=0)
    for _ in range(12):add()
    split=depth//2+1+d['gap_offset']
    for i in range(depth+d['excess']):
        if i==split:
            for _ in range(20):add(ready=1)
        add(v=1,data=80+i,last=i==depth+d['excess']-1,ready=int(i>=split),frame=1)
    for i in range(40):add(ready=int(d['policy']=='ready_first' or i>=12))
    for i in range(3):add(v=1,data=200+i,last=i==2,ready=1,frame=2)
    for _ in range(80):add(ready=1)
    assert tuple(d['semantic_key'])==semantic_key(values,depth)
    return values


def measure(candidate,jobs,protected=()):
    """Independent transaction oracle; inspect only this candidate's native labels."""
    labels={a['label'] for a in validate(candidate)};target={'ready_first':set(),'stalled_first':set()}
    detected=set();triggered=set();fps=[];unknown=[];mapping=[];references={}
    for job in jobs:
        key=f"{job['scene_id']}/{job['revision']}";r=job['result']
        if r['compile_status']!='passed' or r['execution_status']!='completed':unknown.append(key+':native_failure');continue
        tr=s.traces(Path(job['folder']));ref=q.reference(tr,job['depth']);references[key]=ref
        expected=job['rows']
        if len(tr)!=len(expected) or any([v[k] for k in ('cycle','rst','sv','sd','sl','sid','mr')]!=[w['cycle'],w['rst'],w['v'],w['data'],int(w['last']),w['sid'],w['ready']] for v,w in zip(tr,expected)):unknown.append(key+':stimulus_mismatch')
        unknown.extend(key+':'+u for u in ref['unknown'])
        if job['revision']=='after' and ref['events']:unknown.append(key+':fixed_violation')
        cycles={}
        for ev in ref['events']:
            if job['revision']!='before':continue
            eid=f"{job['scene_id']}/frame{ev['frame']}";cycles[ev['first']['cycle']]=eid
            target[job['policy']].add(eid)
            if ev['first']['ready']!=int(job['policy']=='ready_first'):unknown.append(eid+':class_not_exposed')
        def markers(which):
            result=set()
            for item in r[which]:
                if item['id'] not in labels:continue
                match=re.fullmatch(r'cycle=(\d+)',item['detail'].strip())
                if not match:unknown.append(key+':bad_native_marker');continue
                result.add((item['id'],int(match[1])))
            return result
        triggers=markers('triggers');alarms=markers('failures')
        for label,cy in triggers:
            if cy in cycles:
                triggered.add(cycles[cy]);mapping.append(dict(evidence=cycles[cy],obligation=OB,assertion=label,trigger_cycle=cy,detected=(label,cy) in alarms))
        for label,cy in alarms:
            if (label,cy) not in triggers:unknown.append(key+':alarm_without_trigger')
            elif cy in ref['correct_first_cycles']:fps.append(dict(scene=key,label=label,cycle=cy))
            elif cy in cycles:detected.add(cycles[cy])
            else:unknown.append(key+':unresolved_alarm')
    # Both original RTL revisions must exist for every scene, even if one failed.
    for sid in {j['scene_id'] for j in jobs}:
        if not all(f'{sid}/{rev}' in references for rev in ('before','after')):unknown.append(sid+':missing_pair')
    public=target['ready_first'];history=target['stalled_first'];lost=set(protected)-detected
    ordinary=bool(public) and not(unknown or fps or public-detected or public-triggered)
    historical=ordinary and bool(history) and not(history-detected or history-triggered or lost)
    return dict(ordinary_accept=ordinary,historical_accept=historical,detected_ids=sorted(detected),triggered_ids=sorted(triggered),
        public_targets=sorted(public),historical_targets=sorted(history),lost=sorted(lost),false_positives=fps,critical_unknown=unknown,
        obligation_assertion_evidence=mapping,reference=references)


class Controller:
    """One proposal, at most one conditional recovery; irreversible terminal state."""
    def __init__(self,initial,protected):
        self.initial=validate(initial);self.retained=copy.deepcopy(self.initial);self.protected=set(protected)
        self.budget=Budget();self.state='ready';self.proposals=set();self.history=[];self.pending=None
    def reserve(self,request):
        if self.state not in ('ready','history_once'):raise ValueError('terminal_or_inflight')
        stage='shared' if self.state=='ready' else 'recovery'
        self.budget.reserve_call(stage,request,'history_once' if stage=='recovery' else None)
        self.pending=stage;self.state='inflight';return stage
    def response(self,status,value):
        if self.state!='inflight':raise ValueError('not_waiting')
        if status!='response_received':self.state='stop_transport';return None
        try:c=adapt(value)
        except (ValueError,TypeError,KeyError):self.state='stop_interface';return None
        sig=signature(c)
        if sig in self.proposals or sig==signature(self.initial):self.state='stop_repeat';return None
        self.proposals.add(sig);self.budget.reserve_native(self.pending)
        self.state='measuring';return c
    def decision(self,c,m):
        if self.state!='measuring':raise ValueError('not_measuring')
        lost=self.protected-set(m['detected_ids'])
        # Historical acceptance never overrides actual loss/FP/unknown.
        full=bool(m['historical_accept'] and m['ordinary_accept'] and not(lost or m['false_positives'] or m['critical_unknown']))
        if self.pending=='shared':
            self.state=branch('response_received',True,m['ordinary_accept'],full,len(lost),len(m['false_positives']),len(m['critical_unknown']))
            if full:self.retained=copy.deepcopy(c)
        else:
            self.state='recovered' if full else 'stop_recovery_rejects'
            if full:self.retained=copy.deepcopy(c)
        self.history.append(dict(stage=self.pending,decision=self.state,measurement={k:v for k,v in m.items() if k!='reference'},retained_sha256=digest(self.retained)))
        return self.state
    def freeze_for_independent(self,out):
        if self.state!='recovered':raise ValueError('no_recovered_version')
        out.mkdir(parents=True,exist_ok=False)
        s.dump(out/'assertions.json',self.retained)
        s.dump(out/'freeze.json',dict(assertions_sha256=s.sha(out/'assertions.json'),scope='original synchronous FIFO first-presentation atomic drop',historical_evidence=sorted(self.protected)))
        self.budget.reserve_native('independent',recovered=True);self.state='frozen'
        return out/'freeze.json'


def feedback(request,candidate,measured):
    """Only the rejected proposal and measured development diagnostics are added."""
    req=copy.deepcopy(request);req['seed']+=1;body=json.loads(req['messages'][1]['content'])
    body['current_assertions']=candidate
    body['rejection']={k:v for k,v in measured.items() if k not in ('reference','obligation_assertion_evidence')}
    body['historical_development']=compact_reference({k:v for k,v in measured['reference'].items() if '/stalled_first/' in k})
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    return req


def compact_reference(references):
    """Keep sampled first-presentation values and actual transaction endpoints.

    Complete byte records remain in local artifacts. No predicted output or
    correct property is substituted; omission of interior byte records is explicit.
    """
    result={}
    for key,ref in references.items():
        frames=[]
        for fid,f in ref['frames'].items():
            def ends(values):return [] if not values else [values[0],values[-1]]
            frames.append(dict(frame_id_for_diagnosis_only=fid,accepted_count=len(f['accepted']),
                accepted_endpoints=ends(f['accepted']),completed=f['completed'],first_presentation=f['first_presentation'],
                transferred_count=len(f['outputs']),transferred_endpoints=ends(f['outputs']),oversize=f['oversize']))
        result[key]=dict(frames=frames,unknown=ref['unknown'],omitted='interior byte records; complete raw trace retained locally')
    return result


def select_unseen(pool,freeze,out):
    """Do not call during preparation: selection follows a real accepted freeze."""
    meta=s.read(freeze)
    assert s.sha(freeze.parent/'assertions.json')==meta['assertions_sha256']
    rng=random.Random(18732);chosen=[]
    for depth,policy in itertools.product((16,32),q.POLICIES):
        values=[d for d in pool if (d['depth'],d['policy'])==(depth,policy)]
        chosen.extend(rng.sample(values,8))
    s.dump(out/'selected_descriptors.json',chosen)
    s.dump(out/'freeze_binding.json',dict(freeze_sha256=s.sha(freeze),selection_after_freeze=True))
    return chosen


def request(initial,public):
    lock=s.read(LOCK)
    body=dict(task='Generate the entire editable SVA set to repair the supplied current missed first-presentation checks while preserving earlier valid protection. No predicate will be repaired by the framework.',
        specification='FRAME_FIFO1 DROP_WHEN_FULL1, bounded unique-ID completed frames. Oversize frames (>DEPTH accepted bytes with KEEP disabled) must be dropped atomically. Legal nonoversize frames are preserved. Initial reset only. An output first presented under backpressure is correlated with its later handshake before confirming a target.',
        interface=dict(signals=sorted(SIGNALS),obligations=[OB],timing=['same_sample'],
            monitor='input_count and input_complete are passive accepted-input per-TID count/completion BEFORE this edge; first_present=m_axis_tvalid && !output_seen[m_axis_tid]. output_seen updates on any presentation. No expected length or failure bit supplied. All state resets to0.',
            binding='DEPTH is a localparam in the same testbench scope as the generated assertions, not a DUT hierarchy name. Width8 KEEP0 FRAME_FIFO1 DROP_WHEN_FULL1 ID_ENABLE1. Depth8/16/32.',
            sampling='@(posedge clk) disable iff(rst); |-> checks at the same pre-NBA edge. Source presented does not mean accepted. before/after mean RTL revisions, not clock positions. rst cancels checks.',
            expression_grammar='Boolean/arithmetic/bitwise expressions, numeric literals and listed identifiers only. No declarations, functions, IDs, cycle/data whitelist, hierarchical signals or temporal operators. 1..6 properties; multiple properties for the same obligation permitted. Same-sample scope only; alerts outside independently mapped first presentations are unknown.'),
        rtl={rev:(q.P/'frame_fifo_drop'/rev/'axis_fifo.v').read_text() for rev in ('before','after')},
        current_assertions=initial,current_status='Partial editable candidate with historical stalled-first protection and current ready-first misses.',
        public_development=compact_reference(public),output_schema=copy.deepcopy(lock['output_schema']),
        acceptance='Both rules require current ready-first targets, legal-frame correctness guards in all scenes, native trigger/detection and no critical unknown. H additionally preserves stalled-first historical detections. All components editable. H and R equivalent. No independent tests supplied.')
    body['output_schema']['assertions'][0]['timing']='same_sample'
    body['output_schema']['assertions'][0]['obligations']=[OB]
    return dict(**lock['model_parameters'],messages=[lock['system_message'],dict(role='user',content=json.dumps(body,separators=(',',':')))])


def guard(out):
    allowed=[q.P,ARCHIVE,LOCK.parent,q.D/'research185_drop_partial_20261102_r01',q.OLD,out,q.D/'research_native_20261014_r01/tools']
    reads=set()
    def hook(event,args):
        if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('local_only_no_network')
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        path=Path(args[0]).resolve();name=path.as_posix().lower();mode=args[1]
        if any(t in name for t in ('/independent','/holdout','/.secrets/','/.env','/terminal_frozen/','/tested_versions/')):raise RuntimeError('independent_or_secret_material_denied')
        writing=isinstance(mode,str) and any(k in mode for k in 'wax+')
        if writing and path.is_relative_to(q.D) and not path.is_relative_to(out):raise RuntimeError('old_artifact_immutable')
        if not writing and path.is_relative_to(q.D) and not any(path.is_relative_to(p) for p in allowed):raise RuntimeError('outside_development_allowlist')
        if not writing and path.is_relative_to(q.D) and path.is_file() and not path.is_relative_to(out) and '/tools/' not in name:reads.add(path)
    sys.addaudithook(hook)
    return reads


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);reads=guard(out);checks=[]
    def ck(name,ok):
        checks.append(dict(name=name,passed=bool(ok)));s.dump(out/'checks.json',checks)
        if not ok:raise AssertionError(name)
    def rejects(name,fn):
        try:fn()
        except (ValueError,AssertionError,TypeError,KeyError,RuntimeError):ck(name,True);return
        ck(name,False)
    ctl=controls();initial=ctl['partial_stalled']
    for name,c in ctl.items():ck('interface '+name,validate(c)==c)
    ck('same obligation multiple properties',len(validate(ctl['union']))==2)
    for field,value in [('timing','next_sample'),('label','module'),('obligations',['unconfirmed']),('antecedent','cycle==72'),('consequent','dut.DEPTH > 0'),('consequent','DEPTH()'),('consequent','first_present; $finish'),('consequent','input_count=0')]:
        c=copy.deepcopy(initial);c[0][field]=value;rejects('reject '+field+' '+str(value),lambda c=c:validate(c))
    rejects('duplicate label',lambda:validate(initial*2))
    rejects('independent isolation',lambda:(q.D/'research181_presentation_run_20261030_r01/independent/result.json').read_text())
    manifest=s.read(q.P/'source_manifest.json')
    for rev in ('before','after'):
        p=q.P/'frame_fifo_drop'/rev/'axis_fifo.v';entry=next(x for x in manifest if x['path']==s.rel(p))
        ck('source hash '+rev,s.sha(p)==entry['sha256'])
    archived=[]
    for d,p,rev in itertools.product(q.DEPTHS,q.POLICIES,('before','after')):
        folder=ARCHIVE/'native'/str(d)/p/rev
        archived.append(dict(scene_id=f'{d}/{p}',depth=d,policy=p,revision=rev,folder=str(folder),rows=q.rows(d,p),result=s.read(folder/'result.json')))
    baseline=measure(initial,archived);protected=baseline['detected_ids']
    matrices={k:measure(c,archived,protected) for k,c in ctl.items()}
    ck('partial history2 current0',len(protected)==2 and not baseline['ordinary_accept'] and not baseline['critical_unknown'])
    for name in ('union','full'):ck(name+' complete',matrices[name]['historical_accept'])
    ck('replacement actual loss',matrices['replacement_ready']['ordinary_accept'] and len(matrices['replacement_ready']['lost'])==2)
    ck('overbroad legitimate alarms',bool(matrices['overbroad']['false_positives']))
    ck('vacuous rejected',not matrices['vacuous']['ordinary_accept'])
    # Bind actual archived input files, not only regenerated stimuli.
    exclusions=[]
    for root in (q.P/'frame_fifo_drop',q.OLD, q.D/'research185_drop_partial_20261102_r01/prepared',ARCHIVE/'prepared'):
        for path in sorted(root.rglob('*.json')):
            if 'input' not in path.name:continue
            value=s.read(path)
            if isinstance(value,list) and value and isinstance(value[0],dict) and {'cycle','v','frame'}<=set(value[0]):
                for depth in q.DEPTHS:
                    if sum(r['v'] and r['frame']==0 for r in value)==depth-1:
                        exclusions.append(dict(path=s.rel(path),sha256=s.sha(path),semantic_key=list(semantic_key(value,depth))))
    ck('archived development excluded',len(exclusions)>=12)
    used={tuple(v['semantic_key']) for v in exclusions}
    pool=[descriptor(d,p,e,g) for d,p,e,g in itertools.product((16,32),q.POLICIES,range(5,13),(0,1))]
    probes=[descriptor(d,p,6,int(p=='stalled_first')) for d,p in itertools.product((16,32),q.POLICIES)]
    probekeys={tuple(d['semantic_key']) for d in probes}
    reserve=[d for d in pool if tuple(d['semantic_key']) not in used|probekeys]
    ck('64 semantic descriptors',len(pool)==64 and len({tuple(d['semantic_key']) for d in pool})==64)
    ck('60 fresh descriptors after four development probes',len(reserve)==60)
    ck('no payload or timing buys novelty',semantic_key(q.rows(16,'ready_first'),16)==(16,15,20,9,1))
    for d,p in itertools.product((16,32),q.POLICIES):ck(f'{d}/{p} 15 reserved for planned8',sum((x['depth'],x['policy'])==(d,p) for x in reserve)==15)
    s.dump(out/'development_exclusions.json',exclusions)
    s.dump(out/'reserved_semantic_pool.json',reserve)
    s.dump(out/'probe_descriptors.json',probes)
    s.dump(out/'local_controls.json',ctl)
    s.dump(out/'archived_control_results.json',matrices)
    public={k:v for k,v in baseline['reference'].items() if '/ready_first/' in k}
    req=request(initial,public);s.dump(out/'request.preview.json',req)
    ck('common C model system retained',req['messages'][0]==s.read(LOCK)['system_message'] and {k:req[k] for k in ('model','temperature','max_tokens','seed')}==s.read(LOCK)['model_parameters'])
    ck('request excludes historical records and local complete sets','stalled_first/frame' not in req['messages'][1]['content'] and 'all_first' not in req['messages'][1]['content'] and 'first_ready' not in req['messages'][1]['content'])
    # Exhaustive local branch check, explicitly no fabricated model trajectories.
    count=0
    for status,measured,o,h,lost,fp,u in itertools.product(('response_received','timeout'),(False,True),(False,True),(False,True),(0,1),(0,1),(0,1)):
        choice=branch(status,measured,o,h,lost,fp,u)
        expected=status=='response_received' and measured and o and not h and not u and bool(lost or fp)
        ck(f'branch {count}',(choice=='history_once')==expected);count+=1
    def fresh():return Controller(initial,protected)
    for name in ('replacement_ready','union','full','overbroad','vacuous'):
        c=fresh();ck('reserve '+name,c.reserve(req)=='shared')
        proposal=c.response('response_received',dict(assertions=ctl[name],reason='LOCAL HANDWRITTEN FIXTURE'))
        state=c.decision(proposal,matrices[name])
        if name=='replacement_ready':
            ck('extra reject keeps baseline',state=='history_once' and c.retained==initial)
            recovery=feedback(req,proposal,matrices[name]);ck('recovery fits bounded request',len(recovery['messages'][1]['content'].encode())<55000)
            c.reserve(recovery);second=c.response('response_received',dict(assertions=ctl['union'],reason='LOCAL HANDWRITTEN FIXTURE'))
            ck('local branch reaches recovered',c.decision(second,matrices['union'])=='recovered')
            rejects('two calls terminal',lambda:c.reserve(req))
        else:rejects('no recovery '+name,lambda:c.reserve(req))
        rejects('cannot freeze unless recovered '+name,lambda c=c: c.freeze_for_independent(out/'forbidden_freeze')) if name!='replacement_ready' else None
    for status in ('timeout','http_error'):
        c=fresh();c.reserve(req);ck('transport stop '+status,c.response(status,None) is None);rejects('no retry '+status,lambda:c.reserve(req))
    c=fresh();c.reserve(req);c.response('response_received',dict(assertions=initial,reason='repeat'));ck('initial repeat stopped',c.state=='stop_repeat')
    c=fresh();c.reserve(req);c.response('response_received',dict(assertions=ctl['replacement_ready'],reason='fixture'));m=copy.deepcopy(matrices['replacement_ready']);m['critical_unknown']=['unresolved'];ck('unknown stops',c.decision(ctl['replacement_ready'],m)=='stop_unknown')
    c=fresh();c.reserve(req);c.response('response_received',dict(assertions=ctl['replacement_ready'],reason='fixture'));c.decision(ctl['replacement_ready'],matrices['replacement_ready']);c.reserve(feedback(req,ctl['replacement_ready'],matrices['replacement_ready']));c.response('response_received',dict(assertions=ctl['overbroad'],reason='fixture'));ck('failed recovery retains baseline',c.decision(ctl['overbroad'],matrices['overbroad'])=='stop_recovery_rejects' and c.retained==initial)
    b=Budget(clock=lambda:0);bad=copy.deepcopy(req);bad['seed']+=1;rejects('changed sampling',lambda:b.reserve_call('shared',bad));rejects('unauthorized recovery',lambda:b.reserve_call('recovery',req));rejects('independent stage before recovery',lambda:b.reserve_native('independent',True))
    # All native probes and output paths fixed before the first compile.
    s.dump(out/'local_protocol.json',dict(model_calls=0,formal_calls=0,native_compile_budget=8,native_execute_budget=8,probes=probes,
        reserved_pool_count=len(reserve),planned_independent_count=32,per_depth_policy=8,no_replacements=True,
        note='Four probes are DEVELOPMENT, excluded before running. Remaining descriptors are uninstantiated capacity only, not independent results. Same root failure; length/overflow phase combinations do not count as independent bugs.',
        hypothesis='Only if all four predefined development probes confirm both original RTL witness and legal controls, and interface/controller checks pass, seal a two-call pilot; otherwise stop. No adaptive probe replacement.'))
    s.dump(out/'local_protocol_seal.json',{p.name:s.sha(p) for p in out.iterdir() if p.is_file()})
    print('SEALED187 local probes8, no model',flush=True)
    jobs=[];flat=[v[0] for k,v in ctl.items() if k!='union']
    # full, partial, replacement, overbroad, vacuous; one native binary per pair side.
    for index,d in enumerate(probes):
        rows=scene(d)
        for rev in ('before','after'):
            folder=out/'native_probes'/str(index)/rev
            r=s.n.run_native(bench(flat,d['depth'],d['policy'],rows),folder,extra_sources=[q.P/'frame_fifo_drop'/rev/'axis_fifo.v'])
            jobs.append(dict(scene_id=f'probe{index}/{d["depth"]}/{d["policy"]}',depth=d['depth'],policy=d['policy'],revision=rev,folder=str(folder),rows=rows,result=r))
            s.dump(out/'probe_executions.json',jobs);print('NATIVE187',index,rev,r['compile_status'],r['execution_status'],flush=True)
    results={k:measure(c,jobs) for k,c in ctl.items()};s.dump(out/'probe_results.json',results)
    full=results['union'];good=full['historical_accept'] and len(full['public_targets'])==2 and len(full['historical_targets'])==2
    good=good and bool(results['overbroad']['false_positives']) and not results['vacuous']['ordinary_accept']
    good=good and results['replacement_ready']['ordinary_accept'] and not results['replacement_ready']['historical_accept'] and len(results['partial_stalled']['detected_ids'])==2
    s.dump(out/'capacity_decision.json',dict(local_family_viability=bool(good),reserved_descriptors=60,independent_actual_exposure='not_run_not_guaranteed',
        novelty_unit='Accepted frame length and release-gap beat index within a depth/readiness class; ignore payload, TID, seed and absolute cycles.',
        limitations='One defect and a nearby semantic domain. Native probes support family viability, not acceptance of unexecuted reserved descriptors. Future no-exposure/unknown remains failed qualification; no replacement.',
        planned_scope='Width8 KEEP0 unique IDs; Depth16/32; first-presentation atomic oversize drop plus legal prefix/suffix preservation. Initial reset only. Not five-obligation FIFO or global correctness.'))
    protocol=dict(purpose=PURPOSE,eligible=bool(good),model_calls_authorized=0,prospective_max_calls=2,endpoint=ENDPOINT,
        parameters={k:req[k] for k in ('model','temperature','max_tokens','seed')},recovery_seed=req['seed']+1,
        public_rule='All ready-first exposed targets triggered/detected, all legal frames in every scene/revision no false alarms, no critical unknown; independent raw port oracle.',
        historical_rule='Same public rule + historical stalled-first exposed targets + retained baseline evidence IDs. H/R equivalent.',
        protected_ids=protected,branch='One shared proposal. Only O accept, H reject, confirmed lost detection/new legal FP and zero critical unknown permits one recovery. Otherwise stop. No retry; no unused budget transfer; transport failure terminal.',
        limits='1200 seconds per controller, <=60000 UTF8-byte reservation per call and <=120000 total plus included output reservations. This is not measured token usage. Development stage<=12 native jobs; independent stage<=64. Count every attempted compile, including failures.',
        independent='Only full recovery accepted: save candidate/RTL/tool/development hashes before selecting32 reserved descriptors, eight per depth/readiness stratum. No replacements, no feedback from tests; report every exposure/FP/FN/trigger/unknown. Shared both-accept outcome stops without tests under THIS protocol.',
        unchanged='research185 failure and research186 diagnostic qualification unchanged; no model recovery inferred from local union.',
        remote_dispatch='NOT EXECUTED. Future invocation requires a purpose/seal/output-bound explicit grant; this CLI cannot invoke any model.')
    s.dump(out/'pilot_protocol.json',protocol)
    decision=dict(interface_and_branches_passed=True,local_capacity_qualified=bool(good),pilot_sealed=bool(good),action='SEALED_AWAIT_NEW_EXPLICIT_AUTHORIZATION' if good else 'STOP_LOCAL_QUALIFICATION_FAILED',
        model_calls=0,new_model_versions=0,real_extra_rejections=0,new_independent_tests=0,conditional_recovery=dict(numerator=0,denominator=0,estimate=None),tasks2_3_expanded=False)
    s.dump(out/'decision.json',decision)
    s.dump(out/'cost.json',dict(model_calls=0,tokens=0,formal_calls=0,archived_native_jobs_reclassified=12,native_compile_attempts=len(jobs),native_executions=sum(j['result']['native_simulation_calls'] for j in jobs),
        compile_seconds=sum(j['result']['compile']['wall_seconds'] for j in jobs),execution_seconds=sum(j['result'].get('execute',{}).get('wall_seconds',0) for j in jobs)))
    paths=reads|{Path(__file__),Path(q.__file__),Path(s.__file__),Path(s.n.__file__),ROOT/'scripts/research136_prospective_history.py',ROOT/'scripts/research167_adapter_controller.py'}
    s.dump(out/'source_bindings.json',{s.rel(p):s.sha(p) for p in sorted(paths)})
    s.dump(out/'read_audit.json',dict(development_reads=sorted(s.rel(p) for p in reads),independent_contents_read=False,network_calls=0))
    report=['# research187 本地接口、预算分支与独立语义余量核查','',
        '**本地资格成立，可封存有界先导；本轮没有模型调用。**' if good else '**本地资格未全部成立，停止，不进入模型先导。**','',
        f'接口与分支检查{len(checks)}项通过；重判12份既有原生记录，新执行8次编译/仿真。支持同一义务多条性质，所有组件可编辑；显式绑定DEPTH及前沿采样，沿用原始端口参考和首拍适用性规则。',
        '', '64个预定语义描述符按接受帧长度、溢出后排空间隔所在拍及首拍就绪状态去重；4个预定开发探针先排除，剩余60个未实例化描述符（每深度/就绪类15个），未来计划每类8个，共32。payload、ID、随机种子和绝对周期变体不增加余量。',
        '', f'4个开发探针旧RTL确认公共{len(full["public_targets"])}、历史{len(full["historical_targets"])}个目标配置点；联合手写对照接受={full["historical_accept"]}，误报{len(full["false_positives"])}，关键unknown{len(full["critical_unknown"])}。固定版及合法前后帧由独立事务参考检查。探针全部进入开发排除清单，不是独立测试。未运行的60个组合不能声称已曝光或通过。',
        '', '控制器仅在普通接受、历史拒绝、有已确认退化且无关键unknown时允许第二次；拒绝保留原部分候选。传输失败、接口失败、重复提案、双方接受、普通拒绝均停止；恢复失败保留旧保护。冻结和独立选择只开放给完整恢复接受分支。局部手写分支测试不是模型恢复。',
        '', '普通规则与历史规则的合法误报检查范围相同，因而本配置主要可区分旧目标检出损失，不主张新增误报额外拒绝收益。H/R等价；最多2次未来调用，没有本协议授权。原C的公共模型/系统消息/嵌套呈现复用，未读取其成功SVA或独立结果。',
        '', '结论限单个原始同步FIFO丢帧修复、Width8 KEEP关闭、唯一帧ID、Depth16/32、初始化复位及首拍原子丢弃义务。不代表复杂复位取消、全部FIFO义务、形式化证明或跨案例稳定性。新旧证据均为开发已知，不能计搜索新发现。',
        '', '本轮新模型接受0、真实额外拒绝0、恢复0/0不可估计、新独立验收0；任务2/3未扩展，576次搜索负结果不变。下一步只有资格成立并获得新用途授权后才可执行封存先导。',
        '', '本地复现（新输出目录，8次原生执行，无模型）：','```powershell','wsl -- python3 scripts/research187_drop_controller.py --out deliverables/research187_reproduce','```']
    (out/'SUMMARY.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    # Seal every input/controller/report; binaries and logs separately bound by executions.
    s.dump(out/'seal.json',{s.rel(p):s.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and 'obj_dir' not in p.parts})
    print('RESULT187',json.dumps(decision),flush=True)


if __name__=='__main__':
    sys.dont_write_bytecode=True
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    prepare(parser.parse_args().out.resolve())
