"""Original axis_adapter repair: semantic partial protection + fresh trace capacity.

Local qualification only. All four candidate sets are explicitly handwritten.
No model dispatch, fabricated model output, altered RTL or independent execution.
"""
import argparse
from collections import Counter
import copy
import itertools
import json
from pathlib import Path
import re
import shutil
import time
import research159_history_screen as old

ROOT, read, dump, sha = old.ROOT, old.read, old.dump, old.sha
PRIOR = ROOT/'deliverables/research159_history_prepare_20261028_r01'
SIGNALS = {'rst','s_axis_tvalid','s_axis_tready','s_axis_tdata','s_axis_tkeep','s_axis_tlast',
           'm_axis_tvalid','m_axis_tready','m_axis_tdata','m_axis_tkeep','m_axis_tlast'}
OBLIGATIONS={'nonfinal_keep','final_nonempty','stall_valid','stall_payload'}


def controls():
    def p(label,ant,cons,ob,timing='same_sample'):
        return dict(label=label,antecedent=ant,consequent=cons,timing=timing,obligations=[ob])
    nonfinal=p('nonfinal','m_axis_tvalid && m_axis_tready && !m_axis_tlast',"m_axis_tkeep==4'b1111",'nonfinal_keep')
    final=p('final','m_axis_tvalid && m_axis_tready && m_axis_tlast',"m_axis_tkeep!=4'b0000",'final_nonempty')
    holds=[p('hold_valid','m_axis_tvalid && !m_axis_tready','m_axis_tvalid','stall_valid','next_sample'),
           p('hold_payload','m_axis_tvalid && !m_axis_tready','$stable({m_axis_tdata,m_axis_tkeep,m_axis_tlast})','stall_payload','next_sample')]
    return dict(baseline=[nonfinal]+holds,replacement=[final]+holds,complementary=[nonfinal,final]+holds,
                overbroad=[p('full_everywhere','m_axis_tvalid && m_axis_tready',"m_axis_tkeep==4'b1111",'nonfinal_keep')]+holds)


def validate(assertions):
    if not isinstance(assertions,list) or not 1<=len(assertions)<=6:raise ValueError('assertion_count')
    labels=set()
    for a in assertions:
        if set(a)!={'label','antecedent','consequent','timing','obligations'}:raise ValueError('fields')
        if not isinstance(a['label'],str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,39}',a['label']) or a['label'] in labels:raise ValueError('label')
        labels.add(a['label'])
        if a['timing'] not in ('same_sample','next_sample'):raise ValueError('timing')
        if not isinstance(a['obligations'],list) or not a['obligations'] or not set(a['obligations'])<=OBLIGATIONS:raise ValueError('obligations')
        for field in ('antecedent','consequent'):
            s=a[field]
            if not isinstance(s,str) or not s or len(s)>1600:raise ValueError('expression')
            t=re.sub(r"\d+'[hHbBdD][0-9a-fA-F_]+",'0',s)
            if set(re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*',t))-SIGNALS-{'$stable','$past'}:raise ValueError('non_interface_identifier')
            if re.search(r'[^A-Za-z0-9_$\s\[\]:(){}&|!~=<>+\-*/%,^]',t) or re.search(r'(?<![=!<>])=(?!=)|//|/\*|\*/|\+\+|--',t):raise ValueError('not_expression')
    return assertions


def semantic_key(d):
    # Excludes payload, sample IDs and random seed: those cannot buy novelty.
    return (tuple(d['frames']),d['gap'],d['ready_delay'],d['stall_period'],d['reset_at'],d['keep'])


def development():
    rows=[]
    for keep in (0,1):
        for length,delay,gap in itertools.product((1,3,5,9),(8,12),(0,1)):
            rows.append(dict(id=len(rows),frames=[length],gap=gap,ready_delay=delay,stall_period=4,
                             reset_at=-1,keep=keep,scope='history' if keep==0 and length>4 else 'public'))
    rows.append(dict(id=len(rows),frames=[9],gap=0,ready_delay=12,stall_period=4,reset_at=9,keep=1,scope='public'))
    return rows


def capacity(dev):
    # No scenarios are selected or executed. Finite shape counts are audited
    # before any model call. All shapes use a single frame, unlike prior [2,2].
    groups={}
    used={semantic_key(d) for d in dev}
    for name,lengths,keep in [('current_target',(2,),0),('historical_target',(6,7,10,11,12,13),0),
                              ('legal_control',(2,6,7,10,11,12,13),1)]:
        pool=[]
        for length,delay,gap,stall in itertools.product(lengths,range(5,17),(2,3),(2,3,5)):
            d=dict(frames=[length],gap=gap,ready_delay=delay,stall_period=stall,reset_at=-1,keep=keep)
            if semantic_key(d) not in used:pool.append(d)
        groups[name]=dict(available_shapes=len(pool),required=8 if keep==0 else 16,
                         lengths=list(lengths),gap=[2,3],ready_delay=[5,16],stall_period=[2,3,5],keep=keep,
                         novelty='Frame length AND input gap/stall pattern differ from current development. Prior research159/160 use two frames [2,2], not these one-frame shapes.')
    assert all(x['available_shapes']>=x['required'] for x in groups.values())
    return groups


def bench(assertions,scenarios):
    validate(assertions);n=len(scenarios)
    lines=['module tb;bit clk=0;always #5 clk=~clk;bit rst=1;integer cycle=-1, sid=0,phase=0,idx=0,next_allowed=3;bit accepted=0;',
        'bit [7:0] s_axis_tdata=0;bit s_axis_tkeep=0,s_axis_tvalid=0,s_axis_tlast=0;wire s_axis_tready;',
        'wire [31:0] m_axis_tdata;wire [3:0] m_axis_tkeep;wire m_axis_tvalid,m_axis_tlast;bit m_axis_tready=0;',
        'bit [7:0] s_axis_tid=0,s_axis_tdest=0;bit s_axis_tuser=0;wire [7:0] m_axis_tid,m_axis_tdest;wire m_axis_tuser;',
        f'integer lengths[0:{n-1}],gaps[0:{n-1}],delays[0:{n-1}],stalls[0:{n-1}],resets[0:{n-1}],keeps[0:{n-1}];',
        'axis_adapter #(.S_DATA_WIDTH(8),.S_KEEP_ENABLE(0),.S_KEEP_WIDTH(1),.M_DATA_WIDTH(32),.M_KEEP_ENABLE(1),.M_KEEP_WIDTH(4)) dut(.*);']
    for a in assertions:
        op='|->' if a['timing']=='same_sample' else '|=>'
        lines += [f"{a['label']}: assert property (@(posedge clk) disable iff(rst) ({a['antecedent']}) {op} ({a['consequent']})) else $display(\"ASSERT_FAIL {a['label']} cycle=%0d\",$sampled(cycle));",
            f"always @(posedge clk) if(cycle>=0 && !rst && ({a['antecedent']})) $display(\"TRIGGER {a['label']} cycle=%0d\",cycle);"]
    lines+=['initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for i,s in enumerate(scenarios):
        assert len(s['frames'])==1
        lines.append(f"lengths[{i}]={s['frames'][0]};gaps[{i}]={s['gap']};delays[{i}]={s['ready_delay']};stalls[{i}]={s['stall_period']};resets[{i}]={s['reset_at']};keeps[{i}]={s['keep']};")
    lines += [f'for(sid=0;sid<{n};sid=sid+1) begin idx=0;next_allowed=3;for(phase=0;phase<96;phase=phase+1) begin',
        '@(negedge clk);cycle=sid*96+phase;rst=(phase<2)||(resets[sid]>=0 && (phase==resets[sid] || phase==resets[sid]+1));',
        'if(rst) begin idx=0;next_allowed=3;end',
        's_axis_tvalid=!rst && phase>=next_allowed && idx<lengths[sid] && (resets[sid]<0 || phase<resets[sid]);',
        's_axis_tdata=(sid*19+idx+1)%256;s_axis_tlast=(idx==lengths[sid]-1);s_axis_tkeep=keeps[sid];',
        'm_axis_tready=!rst && phase>=delays[sid] && phase%stalls[sid]!=0;',
        '@(posedge clk);accepted=s_axis_tvalid && s_axis_tready && !rst;',
        '$display("TRACE cycle=%0d sid=%0d phase=%0d rst=%0d sv=%0d sr=%0d sd=%0d sk=%0d sl=%0d mv=%0d mr=%0d md=%0d mk=%0d ml=%0d",cycle,sid,phase,rst,s_axis_tvalid,s_axis_tready,s_axis_tdata,s_axis_tkeep,s_axis_tlast,m_axis_tvalid,m_axis_tready,m_axis_tdata,m_axis_tkeep,m_axis_tlast);',
        '#1;if(accepted) begin idx=idx+1;next_allowed=phase+gaps[sid]+1;end',
        'end end @(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule']
    return '\n'.join(lines)


def adjudicate(values):
    queue=[];prev=None;events=[];checks=[];legal=True
    def check(v,ob,e,a):checks.append(dict(cycle=v['cycle'],sid=v['sid'],obligation=ob,expected=e,observed=a,passed=e==a))
    for v in values:
        if v['rst']:
            if queue:events.append(dict(kind='reset_cancel',cycle=v['cycle'],requests=queue.copy()))
            queue=[];prev=None;continue
        if prev and prev['sv'] and not prev['sr'] and (not v['sv'] or any(v[k]!=prev[k] for k in ('sd','sk','sl'))):legal=False
        if prev and prev['mv'] and not prev['mr']:
            check(v,'stall_valid',1,v['mv']);check(v,'stall_payload',[prev[k] for k in ('md','mk','ml')],[v[k] for k in ('md','mk','ml')])
        if v['sv'] and v['sr']:
            request=dict(cycle=v['cycle'],byte=v['sd'],last=v['sl']);queue.append(request);events.append(dict(kind='accepted',**request))
        if v['mv'] and v['mr']:
            check(v,'no_unrequested',True,bool(queue))
            end=next((i+1 for i,x in enumerate(queue[:4]) if x['last']),None)
            count=end if end is not None else min(4,len(queue))
            check(v,'complete_group_or_frame',True,count==4 or end is not None)
            req=queue[:count];queue=queue[count:]
            expected_keep=(1<<count)-1
            check(v,'keep_mask',expected_keep,v['mk'])
            check(v,'frame_boundary',int(end is not None),v['ml'])
            for i,r in enumerate(req):check(v,'byte_order',r['byte'],(v['md']>>(8*i))&255)
            events.append(dict(kind='output',cycle=v['cycle'],sid=v['sid'],requests=req,expected_keep=expected_keep,
                observed_keep=v['mk'],last=v['ml'],mask_corrupt=v['mk']!=expected_keep,
                alignment='Expected frame/packing position; mask mismatch is recorded, not silently considered delivered bytes.'))
        if v['phase']==95:check(v,'drain_complete',0,len(queue))
        prev=v
    return dict(legal=legal,checks=checks,failures=[c for c in checks if not c['passed']],events=events)


def prepare(out):
    old.verify(PRIOR);out.mkdir(parents=True,exist_ok=False)
    for rev in ('before','after'):
        src=PRIOR/'axis_adapter_keep'/rev/'axis_adapter.v';p=out/'rtl'/rev/'axis_adapter.v';p.parent.mkdir(parents=True);shutil.copy2(src,p)
    scenarios=development();dump(out/'scenarios.json',scenarios)
    # Source/old scenario inventory excludes outcomes; old schedule source defines two length2 frames.
    inventory=[]
    for p in (PRIOR/'axis_adapter_keep/stimuli.json',ROOT/'deliverables/research160_history_prepare_20261028_r01/axis_adapter_keep/stimuli.json'):
        oldrows=read(p)
        assert {r['phase'] for r in oldrows if r['sv']}=={3,4,5,6}
        assert {r['phase'] for r in oldrows if r['sv'] and r['sl']}=={4,6}
        inventory.append(dict(path=old.rel(p),sha256=sha(p),frames=[2,2],phases_with_input=[3,4,5,6],role='Observed earlier development shape; include invalid first driver too in exclusions.'))
    dump(out/'prior_shape_inventory.json',inventory)
    dump(out/'future_shape_capacity.json',capacity(scenarios))
    for name,a in controls().items():
        dump(out/'controls'/f'{name}.json',dict(origin='handwritten_local_fixture_not_model',assertions=a))
        (out/'controls'/f'{name}.sv').write_text(bench(a,scenarios))
    tests=[]
    for name,a in controls().items():validate(a);tests.append('valid '+name)
    for bad in ('sid==0','cycle<100','phase==5','expected_keep==1','dut.internal','m_axis_tkeep=0','1; $finish'):
        a=copy.deepcopy(controls()['baseline']);a[0]['antecedent']=bad
        try:validate(a)
        except ValueError:tests.append('reject '+bad)
        else:raise AssertionError(bad)
    a=copy.deepcopy(controls()['complementary']);a.append(dict(a[0],label='another_nonfinal'));validate(a);tests.append('many properties per obligation')
    dump(out/'interface_tests.json',tests)
    dump(out/'protocol.json',dict(case='axis_adapter TKEEP c1c3dc0 original historical repair',
        before='10b6d2f5bc50f965d6aee213415b60f1f9af58e5',after='c1c3dc0b66e98a186878b32a4d65cdcd00eaa358',
        source='Pinned original files verified in research159/161; no local fault injection or RTL edit.',
        selection=[dict(case='ibex54',status='excluded',reason='Mandatory new semantic target codes exhausted; research164 stop preserved'),
                   dict(case='axis_adapter_keep',status='selected_for_native_qualification',reason='Original repair spans full nonfinal and partial final output groups; temporal/frame shapes not finite exhausted decoder words'),
                   dict(case='axis_fifo_pause',status='not_selected',reason='Only one exposed pause-valid protection class in prior evidence; no proven second current gap')],
        fixed_config='8->32 bit, S_KEEP_ENABLE0, M_KEEP_ENABLE1; no downsize or async RTL',
        public='keep=0 single short frames of1/3 bytes, plus ALL keep=1 legal frames of1/3/5/9 bytes and reset cancellation control',
        history='keep=0 single long frames of5/9 bytes. Exact original target failure exposure required, including nonfinal groups protected by baseline.',
        reference='Independent accepted-byte queue, expected packing mask/data/frame/end, stall and reset checks. Candidate is never correctness oracle.',
        baseline='Handwritten nonfinal full-mask+stall properties, all editable. No model-proposal or natural-regression-rate claim.',
        controls='semantic replacement final-only; complementary union; overbroad full-mask on every beat',
        rule_O='Native success, public target violation cycles detected and triggered; no assertion failure on correct samples of either original RTL version; unknown rejects.',
        rule_H='Same O plus historical target cycles detected/triggered and no new historical false positives. Record loss of baseline detections separately.',
        local_cap=dict(compiles=8,executions=8,models=0),data='All33 scenarios are development; no new independent traces selected or run.',
        independent='After real accepted recovery freezes: sample32 unused semantic shapes (8 short targets,8 long targets,16 legal), using source/shape exclusions; require real target exposure in both obligations, keep candidate frozen. Unknown or no exposure fails. No payload-only novelty.'))
    dump(out/'code_bindings.json',{old.rel(p):sha(p) for p in (Path(__file__),Path(old.__file__),Path(old.native.__file__))})
    dump(out/'seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    print('PREPARED165',len(scenarios),'development scenarios;capacity',capacity(scenarios),flush=True)


def verify(prep):
    for n,h in read(prep/'seal.json').items():assert sha(prep/n)==h,n
    for n,h in read(prep/'code_bindings.json').items():assert sha(ROOT/n)==h,n


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False);results=[]
    for name in controls():
        for rev in ('before','after'):
            folder=out/name/rev
            result=old.native.run_native((prep/'controls'/f'{name}.sv').read_text(),folder,extra_sources=[prep/'rtl'/rev/'axis_adapter.v'])
            if result['execution_status']=='completed':
                vals=old.trace(folder);oracle=adjudicate(vals);dump(folder/'trace.json',vals);dump(folder/'oracle.json',oracle)
            results.append(dict(control=name,revision=rev,result=result));dump(out/'progress.json',results)
            print('NATIVE165',name,rev,result['compile_status'],result['execution_status'],len(result.get('failures',[])),flush=True)
    dump(out/'results.json',results);verify(prep)


def positions(items):return {int(re.fullmatch(r'cycle=(\d+)',r['detail'])[1]) for r in items}


def report(prep,executed,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False)
    scenarios=read(prep/'scenarios.json');runs=read(executed/'results.json');evidence={};checks=[];mappings=[]
    costs=dict(model_calls=0,formal_calls=0,native_compiles=len(runs),native_executions=0,compile_seconds=0.,execute_seconds=0.)
    def check(name,value):checks.append(dict(name=name,passed=bool(value)));assert value,name
    for r in runs:
        name,rev,n=r['control'],r['revision'],r['result'];folder=executed/name/rev
        costs['native_executions']+=n['native_simulation_calls'];costs['compile_seconds']+=n['compile']['wall_seconds'];costs['execute_seconds']+=n.get('execute',{}).get('wall_seconds',0)
        check('native completed '+name+rev,n['compile_status']=='passed' and n['execution_status']=='completed')
        vals=old.trace(folder);oracle=adjudicate(vals);check('oracle saved '+name+rev,oracle==read(folder/'oracle.json'))
        check('legal inputs '+name+rev,oracle['legal'])
        check('complete scope '+name+rev,len(vals)==len(scenarios)*96)
        if rev=='after':check('fixed independent oracle clean '+name,not oracle['failures'])
        else:check('original failures only TKEEP '+name,oracle['failures'] and all(f['obligation']=='keep_mask' for f in oracle['failures']))
        fail=positions(n['failures']);trigger=positions(n['triggers']);targets={f['cycle'] for f in oracle['failures']}
        evidence[name,rev]=dict(vals=vals,oracle=oracle,fail=fail,trigger=trigger,targets=targets)
        for a in read(prep/'controls'/f'{name}.json')['assertions']:
            mappings.append(dict(control=name,revision=rev,label=a['label'],obligations=a['obligations'],
                triggers=sorted(positions([f for f in n['triggers'] if f['id']==a['label']])),
                failures=sorted(positions([f for f in n['failures'] if f['id']==a['label']]))))
    inputkeys=('cycle','sid','phase','rst','sv','sd','sk','sl','mr')
    for name in controls():
        a,b=evidence[name,'before'],evidence[name,'after']
        check('same actual inputs '+name,all(all(x[k]==y[k] for k in inputkeys) for x,y in zip(a['vals'],b['vals'])))
        for rev in ('before','after'):check('candidate does not change RTL '+name+rev,evidence[name,rev]['vals']==evidence['baseline',rev]['vals'])
    a=evidence['baseline','before'];alltargets=a['targets']
    pub={c for c in alltargets if scenarios[a['vals'][c]['sid']]['scope']=='public'};hist=alltargets-pub
    protected=a['fail']&hist;matrix=[]
    for name in controls():
        v=evidence[name,'before'];w=evidence[name,'after'];fp=(v['fail']-v['targets'])|w['fail']
        O=not(pub-v['fail'] or pub-v['trigger'] or fp)
        H=O and not(hist-v['fail'] or hist-v['trigger'])
        matrix.append(dict(control=name,origin='handwritten_local_qualification',ordinary=O,history=H,
            public_detected=len(pub&v['fail']),public_exposed=len(pub),historical_detected=len(hist&v['fail']),historical_exposed=len(hist),
            baseline_protected=len(protected),lost_prior_detections=sorted(protected-v['fail']),false_positive_cycles=len(fp),
            public_untriggered=len(pub-v['trigger']),history_untriggered=len(hist-v['trigger']),unknown=0))
    by={r['control']:r for r in matrix}
    check('baseline actual history protection and public miss',len(protected)>0 and by['baseline']['public_detected']==0 and by['baseline']['false_positive_cycles']==0)
    check('non-whitelist discriminator',by['replacement']['ordinary'] and not by['replacement']['history'] and by['replacement']['lost_prior_detections'])
    check('joint positive control',by['complementary']['history'])
    check('legal partial output rejects overbroad',not by['overbroad']['ordinary'] and by['overbroad']['false_positive_cycles']>0)
    capacity_result=read(prep/'future_shape_capacity.json');check('fresh capacity remains',all(v['available_shapes']>=v['required'] for v in capacity_result.values()))
    witnesses=[]
    for kind,ids in [('current',pub),('historical_nonfinal',protected)]:
        c=min(ids);vb=a['vals'];vf=evidence['baseline','after']['vals']
        witnesses.append(dict(kind=kind,cycle=c,scenario=scenarios[vb[c]['sid']],before=vb[max(0,c-1):c+2],after=vf[max(0,c-1):c+2],
            reference=[e for e in a['oracle']['events'] if e.get('cycle')==c],
            baseline_detected=c in a['fail'],baseline_triggered=c in a['trigger'],replacement_detected=c in evidence['replacement','before']['fail']))
    dump(out/'acceptance_matrix.json',matrix);dump(out/'witnesses.json',witnesses);dump(out/'obligation_map.json',mappings)
    dump(out/'retained_baseline.json',dict(path=old.rel(prep/'controls/baseline.json'),sha256=sha(prep/'controls/baseline.json'),retained_native_detections=sorted(protected),remaining_public_misses=sorted(pub),
        note='Historical rejection of handwritten replacement retains unchanged partial baseline; not a real model journal.'))
    dump(out/'costs.json',costs);dump(out/'checks.json',checks)
    pilot=out/'pilot';pilot.mkdir()
    body=dict(task='Return complete editable SVA assertion set; repair public original TKEEP misses while retaining prior correct protections. Model selects all predicates. No fixed protected component.',
        rtl={rev:(prep/'rtl'/rev/'axis_adapter.v').read_text() for rev in ('before','after')},
        config=dict(S_DATA_WIDTH=8,S_KEEP_ENABLE=0,S_KEEP_WIDTH=1,M_DATA_WIDTH=32,M_KEEP_ENABLE=1,M_KEEP_WIDTH=4),
        semantics='At posedge clk, source transfers only when valid&&ready. Source holds pending payload during stall. Reset cancels pending packing. Disabled input keep means every accepted input byte valid regardless of s_axis_tkeep. Nonfinal output groups are full; final groups may be partial but must contain valid bytes. Output stays stable through backpressure until acceptance unless reset.',
        obligations=dict(nonfinal_keep='Accepted nonfinal output must have all lanes valid.',final_nonempty='Accepted final output contains valid bytes; partial final groups are permitted.',stall_valid='Presented valid remains until handshake unless reset.',stall_payload='Presented payload/keep/last stable through stall unless reset.'),
        current_assertions=read(prep/'controls/baseline.json')['assertions'],origin='Explicitly handwritten partial seed, not archived model generation. All properties editable.',
        output_contract='JSON with assertions and reason. 1..6 assertions with label,antecedent,consequent,timing(same_sample/next_sample),obligations. Interface signals only; sampled $stable/$past allowed. Multiple properties per obligation permitted. No sample IDs, oracle/queue variables or declarations.',
        acceptance='Same native public checks for both policies; added-history policy checks historical protections. Unknown rejects. Only actual native behavior establishes detection.',
        public_development_evidence=[])
    for c in sorted(pub)[:6]:
        body['public_development_evidence'].append(dict(before=a['vals'][c],after=evidence['baseline','after']['vals'][c],
            oracle=[f for f in a['oracle']['failures'] if f['cycle']==c],candidate_failed=c in a['fail'],candidate_triggered=c in a['trigger']))
    # Add legal partial masks so ordinary controls are not merely positive targets.
    legal_outputs=[e for e in evidence['baseline','after']['oracle']['events'] if e['kind']=='output' and
                   scenarios[e['sid']]['scope']=='public' and scenarios[e['sid']]['keep']==1]
    body['public_legal_outputs']=[dict(sample=evidence['baseline','after']['vals'][e['cycle']],reference=e) for e in legal_outputs[:6]]
    req=dict(model='deepseek/deepseek-v3-0324',seed=16507,temperature=0.2,max_tokens=1024,
        messages=[dict(role='system',content='Generate the SVA JSON expressions yourself, without semantic repair by the frontend.'),dict(role='user',content=json.dumps(body,separators=(',',':')))])
    dump(pilot/'request.preview.json',req)
    dump(pilot/'protocol.json',dict(status='sealed_local_qualification_only_no_authorization',endpoint='https://api.highwayapi.ai/openai/chat/completions',
        model=req['model'],seeds=[16507,16508],temperature=0.2,max_output_tokens=1024,max_calls=2,retries=0,
        branch='One shared real proposal. Only O accept/H reject + actual lost baseline detection or new legal false positive + no critical unknown permits ONE history-feedback recovery. Otherwise stop; no reseeding/quota transfer/automatic expansion.',
        common_generation='Same exact shared request and editable expression adapter; only historical checks and resulting feedback differ.',
        target_rules=read(prep/'protocol.json'),
        future_independent=dict(count=32,strata=capacity_result,selection_seed=16509,
            stage='Only after REAL recovered version passes all current/historical native gates: freeze first, then draw unused shapes. No current or archived successful fixture sent to model.',
            novelty_key='frames,gap,ready_delay,stall_period,reset_at,keep; exclude all executed development descriptors and reject identical actual accepted-transaction/ready/reset signatures. Ignore payload as a novelty source.',
            requirement='8 short original violations,8 long original violations,16 legal traces; both original/after RTL; actual exposure, necessary trigger, no false positive/miss/unknown. Full failures retained; no feedback after test.',
            no_reroll='If selected shape duplicates, lacks exposure or fails, preserve as failure/unknown and stop. No replacement tests or relaxed standard.'),
        native_budget=dict(development_compiles=4,development_executions=4,independent_compiles=2,independent_executions=2),
        limitation='Handwritten structural qualification only, no natural model regression rate. Added-history value only; no R-over-H claim.',
        funding='No model calls authorized by local qualification; obtain new purpose-bound authorization after executable controller/preflight verified.'))
    dump(pilot/'bindings.json',dict(prepared_seal=sha(prep/'seal.json'),native_results=sha(executed/'results.json'),baseline=sha(prep/'controls/baseline.json'),request=sha(pilot/'request.preview.json'),source=sha(Path(__file__))))
    dump(pilot/'seal.json',{p.name:sha(p) for p in pilot.iterdir() if p.is_file()})
    dump(out/'decision.json',dict(local_partial_qualification=True,semantic_discrimination=True,fresh_capacity=True,pilot_protocol_sealed=True,
        model_calls=0,real_incremental_rejections=0,real_recoveries=0,new_independent_runs=0,conditional_recovery='0/0 not estimable',
        stage='Await executable runtime integration/preflight then explicit model authorization; protocol/request seal is not a claim of running controller.'))
    lines=['# axis_adapter 原始历史修复：三项同时资格验证', '',
        '**部分保护、非白名单区分和未用语义场景容量三项成立，先导协议与请求已封存；模型调用0。**', '',
        '选择原有可靠候选中的 axis_adapter TKEEP 修复（父提交10b6d2f5bc50f965d6aee213415b60f1f9af58e5 → c1c3dc0b66e98a186878b32a4d65cdcd00eaa358）。原始RTL未修改。Ibex #54 因独立目标空间耗尽继续停止；FIFO pause 尚无第二个曝光缺口，不为制造差异改动设计。', '',
        '固定8→32位、输入KEEP禁用、输出KEEP启用。独立队列以握手接受事件对齐字节、输出组、帧边界与复位取消；检查完整掩码、数据、排空及背压。输出掩码错误单独记录，不把错误掩码下的字节偷偷认作有效交付。', '',
        '|手写资格对照|当前目标检出|历史全部曝光检出|丢失基线检出|误报周期|O/H|', '|---|---:|---:|---:|---:|---|']
    for r in matrix:lines.append(f"|{r['control']}|{r['public_detected']}/{r['public_exposed']}|{r['historical_detected']}/{r['historical_exposed']}|{len(r['lost_prior_detections'])}|{r['false_positive_cycles']}|{r['ordinary']}/{r['history']}|")
    lines += ['', f'基线实际保护 {len(protected)} 个非末拍原始违例采样，遗漏 {len(pub)} 个公共末拍违例。replacement按端口TLAST语义替换性质，O接受而H额外拒绝；拒绝保留原基线和既有检出。complementary只是手写可满足性正对照，不计模型自动恢复。overbroad在合法短帧上被拒绝，普通规则并非只看目标检出。所有性质均可编辑。', '',
        f'{len(scenarios)} 个开发场景，每个96周期；公共合法控制同时包含长短帧与复位取消。每组前后实际合法输入一致，固定版本独立检查无失败，旧版失败只来自原始TKEEP缺陷。样本数不是独立Bug数；同一修复的末拍/非末拍是保护类别，不声称两个历史Bug。', '',
        '## 独立场景空间先行检查', '',
        '|分层|当前尚未运行的结构候选数|未来需要|', '|---|---:|---:|']
    for k,v in capacity_result.items():lines.append(f"|{k}|{v['available_shapes']}|{v['required']}|")
    lines += ['', '独立候选按帧长度、输入间隔、背压延迟/周期、复位及KEEP配置去重；不以数据值、种子或样本编号获取新颖性。新池的输入间隔2/3、背压周期2/3/5与当前开发间隔0/1、周期4不同，长度也取未用于本轮的2及6/7/10/11/12/13。旧research159/160为两帧[2,2]，列入排除清单。',
        '这里只核查可用结构数量，未生成选定的32个独立测试、未跑波形，也没有预先宣称它们都将曝光目标。未来冻结后必须再核对实际接受轨迹不重复且目标真正曝光；重复、无曝光或失败都按原协议停止，不能补抽成功测试。', '',
        '## 封存与边界', '',
        '最多2次未来真实调用：共享提案一次，仅出现O接受/H拒绝且确认退化、无关键unknown时恢复一次。恢复完整接受后才冻结、生成新独立测试。不重试，不自动扩种子。当前只完成资格与协议封存，尚需将新接口接入实际预算控制器并完成本地预检，再申请明确调用授权。',
        f"原生编译{costs['native_compiles']}次、执行{costs['native_executions']}次；编译墙钟{costs['compile_seconds']:.3f}s、执行{costs['execute_seconds']:.3f}s。没有模型/形式化调用、新接受模型版本或新独立验收。条件恢复仍0/0。", '',
        '旧Ibex停止结果、FIFO指定范围验收、stat unknown及576查询负结果均保持不变。本轮不把已知TKEEP缺口重新记成契约搜索新增发现。', '',
        '```powershell',
        'wsl -- python3 scripts/research165_adapter_qualification.py prepare --out deliverables/research165_prepare_new',
        'wsl -- python3 scripts/research165_adapter_qualification.py run --prepared deliverables/research165_prepare_new --out deliverables/research165_native_new',
        'wsl -- python3 scripts/research165_adapter_qualification.py report --prepared deliverables/research165_prepare_new --executed deliverables/research165_native_new --out deliverables/research165_report_new',
        '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
    dump(out/'seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(matrix=matrix,capacity=capacity_result,checks=len(checks),costs=costs),indent=2),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','report'])
    for name in ('prepared','executed','out'):ap.add_argument('--'+name,type=Path,required=name=='out')
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='run':run(a.prepared.resolve(),a.out.resolve())
    else:report(a.prepared.resolve(),a.executed.resolve(),a.out.resolve())
