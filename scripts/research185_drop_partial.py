"""Local partial-protection qualification on original synchronous FIFO drop fix.

All assertions are handwritten diagnostics. No model, independent test or pilot.
One transaction is one target even when it leaks multiple beats.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import research183_history_screen as s

ROOT=s.ROOT;D=s.D
P=D/'research183_history_prepare_20261101_r01'
OLD=D/'research184_fifo_fixture_repair_20261101_r01'
DEPTHS=(8,16,32)
POLICIES=('ready_first','stalled_first')
PROPERTIES={
    'first_stalled':dict(antecedent='first_present && !m_axis_tready',consequent='input_complete && input_count <= DEPTH'),
    'first_ready':dict(antecedent='first_present && m_axis_tready',consequent='input_complete && input_count <= DEPTH'),
    'all_first':dict(antecedent='first_present',consequent='input_complete && input_count <= DEPTH'),
    'overbroad_one':dict(antecedent='first_present',consequent='input_complete && input_count == 1'),
    'never':dict(antecedent="first_present && 1'b0",consequent='input_complete && input_count <= DEPTH')}
CONTROLS={'partial_stalled':['first_stalled'],'replacement_ready':['first_ready'],
          'union':['first_stalled','first_ready'],'full':['all_first'],
          'overbroad':['overbroad_one'],'vacuous':['never']}


def rows(depth,policy):
    values=copy.deepcopy(s.fifo_rows(depth))
    tail=next(v['cycle'] for v in values if v['frame']==1 and v['last'])
    for v in values:
        v['sid']=v['frame']+1 if v['v'] else 0
        if policy=='stalled_first' and tail<v['cycle']<=tail+12:v['ready']=0
    return values


def bench(depth,policy):
    text=s.common_sv(1,1,8)+f'localparam DEPTH={depth};\n'
    text+='axis_fifo #(.DEPTH(DEPTH),.DATA_WIDTH(8),.KEEP_ENABLE(0),.FRAME_FIFO(1),.DROP_WHEN_FULL(1),.ID_ENABLE(1)) dut(.*);\n'
    text+='''// Passive event bookkeeping, no precomputed expected values or failure bits.
integer ingress_count[0:255];bit ingress_complete[0:255];bit output_seen[0:255];integer j;
wire first_present=m_axis_tvalid && !output_seen[m_axis_tid];
wire [31:0] input_count=ingress_count[m_axis_tid];
wire input_complete=ingress_complete[m_axis_tid];
always @(posedge clk) begin
 if(rst) begin for(j=0;j<256;j=j+1) begin ingress_count[j]<=0;ingress_complete[j]<=0;output_seen[j]<=0;end end
 else begin
  if(s_axis_tvalid && s_axis_tready) begin ingress_count[s_axis_tid]<=ingress_count[s_axis_tid]+1;if(s_axis_tlast) ingress_complete[s_axis_tid]<=1;end
  if(m_axis_tvalid) output_seen[m_axis_tid]<=1;
 end
end
'''
    for label,p in PROPERTIES.items():
        text+=f'''{label}: assert property (@(posedge clk) disable iff(rst) ({p['antecedent']}) |-> ({p['consequent']})) else $display("ASSERT_FAIL {label} cycle=%0d",$sampled(cycle));
always @(posedge clk) if(!rst && ({p['antecedent']})) $display("TRIGGER {label} cycle=%0d",cycle);
'''
    text+='initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);\n'
    for r in rows(depth,policy):
        text+=f"@(negedge clk);cycle={r['cycle']};rst={r['rst']};s_axis_tvalid={r['v']};s_axis_tdata={r['data']};s_axis_tlast={int(r['last'])};s_axis_tid={r['sid']};m_axis_tready={r['ready']};\n"
        text+='@(posedge clk);$display("TRACE cycle=%0d rst=%0d sv=%0d sr=%0d sd=%0d sl=%0d sid=%0d dest=%0d mv=%0d mr=%0d md=%0d ml=%0d mid=%0d ov=%0d good=%0d first=%0d cnt=%0d done=%0d",cycle,rst,s_axis_tvalid,s_axis_tready,s_axis_tdata,s_axis_tlast,s_axis_tid,s_axis_tdest,m_axis_tvalid,m_axis_tready,m_axis_tdata,m_axis_tlast,m_axis_tid,status_overflow,status_good_frame,first_present,input_count,input_complete);\n'
    return text+'@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule\n'


def guard(out):
    seen=set();denied=[]
    allowed=(P,OLD,D/'research183_screen_audit_20261101_r01',out)
    def hook(event,args):
        if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('no_network')
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        p=Path(args[0]).resolve();name=p.as_posix().lower();mode=args[1]
        writing=isinstance(mode,str) and any(k in mode for k in 'wax+')
        if any(x in name for x in ('/independent','/holdout','/.secrets/','/.env','/tested_versions/','/terminal_frozen/')):
            denied.append(str(p));raise RuntimeError('excluded_material')
        if writing:
            if p.is_relative_to(D) and not p.is_relative_to(out):raise RuntimeError('immutable_old_records')
        elif p.is_relative_to(D):
            tools=D/'research_native_20261014_r01/tools'
            if not any(p.is_relative_to(a) for a in allowed+(tools,)):
                denied.append(str(p));raise RuntimeError('excluded_material')
            if not p.is_relative_to(out):seen.add(p)
    sys.addaudithook(hook)
    return seen,denied


def reference(tr,depth):
    """Python event reconstruction, independent of DUT and evaluated predicates."""
    counts={};done=set();first_seen=set();frames={};firsts={};events=[];unknown=[];correct=set();violating=set();last=None
    for v in tr:
        cy=v['cycle'];mid=v['mid']
        if v['rst']:
            counts.clear();done.clear();first_seen.clear();last=None;continue
        if last and last['sv'] and not last['sr'] and any(v[k]!=last[k] for k in ('sv','sd','sl','sid')):unknown.append(f'illegal_source:{cy}')
        if (v['cnt'],v['done'],v['first'])!=(counts.get(mid,0),int(mid in done),int(bool(v['mv']) and mid not in first_seen)):
            unknown.append(f'passive_monitor_mismatch:{cy}')
        if v['mv'] and mid not in first_seen:
            first_seen.add(mid);firsts[mid]=dict(cycle=cy,ready=v['mr'],input_count=counts.get(mid,0),input_complete=mid in done)
            if mid not in frames or mid not in done:unknown.append(f'uncorrelated_output:{cy}')
            elif counts[mid]>depth:violating.add(cy)
            else:correct.add(cy)
        if v['sv'] and v['sr']:
            sid=v['sid']
            if sid in done:unknown.append(f'reused_completed_frame_id:{cy}')
            counts[sid]=counts.get(sid,0)+1
            frames.setdefault(sid,dict(accepted=[],outputs=[]))['accepted'].append(dict(cycle=cy,data=v['sd'],last=v['sl']))
            if v['sl']:done.add(sid)
        if v['mv'] and v['mr']:
            if mid not in frames:unknown.append(f'unmatched_handshake:{cy}')
            else:frames[mid]['outputs'].append(dict(cycle=cy,data=v['md'],last=v['ml']))
        last=v
    for fid,f in frames.items():
        f['completed']=fid in done;f['first_presentation']=firsts.get(fid);f['oversize']=len(f['accepted'])>depth
        if fid not in done:unknown.append(f'incomplete_input:{fid}')
        if f['oversize']:
            # Require actual later transfer to corroborate early stalled alarms.
            if fid in firsts and not f['outputs']:unknown.append(f'presented_not_transferred:{fid}')
            if f['outputs']:events.append(dict(frame=fid,obligation='oversize_frame_atomic_drop',first=firsts[fid],accepted=f['accepted'],outputs=f['outputs']))
        else:
            if [(r['data'],r['last']) for r in f['accepted']]!=[(r['data'],r['last']) for r in f['outputs']]:unknown.append(f'legal_frame_not_preserved:{fid}')
        # Match every emitted byte back to the original accepted frame; not to
        # an assumed FIFO position after a corrupt frame has shifted the queue.
        lookup={r['data']:r for r in f['accepted']}
        if len(lookup)!=len(f['accepted']):unknown.append(f'ambiguous_byte_identity:{fid}')
        for o in f['outputs']:
            if o['data'] not in lookup or lookup[o['data']]['cycle']>o['cycle'] or lookup[o['data']]['last']!=o['last']:
                unknown.append(f'wrong_frame_data_or_tag:{fid}:{o["cycle"]}')
    return dict(frames=frames,events=events,correct_first_cycles=sorted(correct),violation_first_cycles=sorted(violating),unknown=unknown)


def local_checks():
    checks=[]
    def ck(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for depth in DEPTHS:
        a,b=rows(depth,'ready_first'),rows(depth,'stalled_first')
        ck(f'{depth} only sink policy differs',all({k:v for k,v in x.items() if k!='ready'}=={k:v for k,v in y.items() if k!='ready'} for x,y in zip(a,b)))
        ck(f'{depth} twelve predetermined stall cycles',sum(x['ready']!=y['ready'] for x,y in zip(a,b))==12)
        for policy in POLICIES:
            source=bench(depth,policy)
            ck(f'{depth}/{policy} numeric literals',not re.search(r'\b(True|False)\b',source))
            ck(f'{depth}/{policy} native asserts',source.count('assert property')==len(PROPERTIES))
    for label,p in PROPERTIES.items():
        ck(label+' no scenario/data/cycle whitelist',not any(w in p['antecedent']+p['consequent'] for w in ('cycle','sid','mid','tdata','scenario')))
    return checks


def execute(out):
    out.mkdir(parents=True,exist_ok=False);seen,denied=guard(out);prep=out/'prepared';prep.mkdir();checks=local_checks()
    def ck(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    # Guard probe denied before any independent contents are opened.
    try:(D/'research181_presentation_run_20261030_r01/independent/C/result.json').read_bytes()
    except RuntimeError as e:ck('independent read blocked',str(e)=='excluded_material')
    for rev in ('before','after'):
        path=P/'frame_fifo_drop'/rev/'axis_fifo.v'
        original=next(x for x in s.read(P/'source_manifest.json') if x['path']==s.rel(path))
        ck('original RTL unchanged '+rev,s.sha(path)==original['sha256'])
    s.dump(prep/'population.json',dict(depths=list(DEPTHS),sink_policies=list(POLICIES),controls=CONTROLS,
         ordering='Fixed before native runs; depth8 retained as no-witness control; no replacement or adaptive scene selection.',
         candidate_origin='handwritten local diagnostic, not a model-generated candidate',mechanism='one original drop-state persistence defect; temporal output-readiness classes are not independent bugs'))
    s.dump(prep/'properties.json',PROPERTIES)
    s.dump(prep/'protocol.json',dict(model_calls=0,network_calls=0,formal_calls=0,native_compile_budget=12,native_execution_budget=12,retries=0,
        source='Same original a9c04a4 parent/fix. ID_ENABLE=1 is a supported parameter; frame IDs unique within reset epoch. No RTL edits. DATA_WIDTH8, KEEP disabled, FRAME_FIFO1, DROP_WHEN_FULL1.',
        monitor='Generic per-TID accepted-beat count, input TLAST completion, and first output presentation. No expected lengths, fault bits, cycle/scenario IDs or answer table. Python reference reconstructs from raw ports and checks monitor fields.',
        split='Two separately run transaction contexts: first leaked output already ready (public) versus first leaked output stalled (history). Both later handshake. First-presentation classification must agree with the preselected sink policy; otherwise unknown.',
        evidence_unit='One input frame, not each leaked byte/cycle. Do not count early detection and later handshake as separate targets. Depth variants are exposure configurations, not separate mechanisms.',
        ordinary='All exposed ready-first target frames detected with actual native trigger. All correct frames in ALL scenarios/RTL revisions guarded against false alarms. No critical unknown; fixed reference must pass.',
        historical='Same O plus stalled-first target-frame detections and triggers, and preservation of baseline detection IDs. H/R equivalent.',
        controls='Partial checks only first stalled presentation; replacement checks only first ready presentation; union/full cover both. Overbroad legal-FP and vacuous negatives retained. All properties editable; union is not real recovery.',
        stopping='Exactly12 native attempts then report. No models, successful-assertion retrieval, independent tests, model request or pilot authorization. Structural qualification alone does not establish model recovery.',
        limits='Unique frame IDs and unique payload bytes within frame required for correlation. No ID reuse, async clocks, sparse KEEP, unbounded fairness or formal proof. Fresh semantic independent-test capacity not certified here.'))
    for depth in DEPTHS:
        for policy in POLICIES:
            (prep/f'tb_{depth}_{policy}.sv').write_text(bench(depth,policy))
            s.dump(prep/f'inputs_{depth}_{policy}.json',rows(depth,policy))
    s.dump(prep/'checks.json',checks)
    s.dump(prep/'source_bindings.json',{s.rel(p):s.sha(p) for p in [Path(__file__),Path(s.__file__),Path(s.n.__file__),P/'source_manifest.json']+
        [P/'frame_fifo_drop'/r/'axis_fifo.v' for r in ('before','after')]})
    s.dump(prep/'seal.json',{p.name:s.sha(p) for p in prep.iterdir() if p.is_file()})
    print('SEALED185 6 pairs, 6 controls, no model',flush=True)
    jobs=[]
    for depth in DEPTHS:
        for policy in POLICIES:
            for rev in ('before','after'):
                result=s.n.run_native((prep/f'tb_{depth}_{policy}.sv').read_text(),out/'native'/str(depth)/policy/rev,
                    extra_sources=[P/'frame_fifo_drop'/rev/'axis_fifo.v'])
                jobs.append(dict(depth=depth,policy=policy,revision=rev,result=result));s.dump(out/'executions.json',jobs)
                print('NATIVE185',depth,policy,rev,result['compile_status'],result['execution_status'],flush=True)
    report=out/'report';report.mkdir();refs={};native={};unknown=[];targets={'ready_first':set(),'stalled_first':set()};pairs=[];mapping=[]
    for job in jobs:
        depth,policy,rev=job['depth'],job['policy'],job['revision'];key=f'{depth}/{policy}/{rev}';folder=out/'native'/key
        r=job['result'];native[key]=r
        if r['compile_status']!='passed' or r['execution_status']!='completed':unknown.append(key+':native_failure');continue
        tr=s.traces(folder);expected=rows(depth,policy)
        ck('exact driven rows '+key,len(tr)==len(expected) and all([a[k] for k in ('cycle','rst','sv','sd','sl','sid','mr')]==[b['cycle'],b['rst'],b['v'],b['data'],int(b['last']),b['sid'],b['ready']] for a,b in zip(tr,expected)))
        ref=reference(tr,depth);refs[key]=ref;unknown.extend(key+':'+x for x in ref['unknown']);s.dump(report/(key.replace('/','_')+'_transactions.json'),ref)
        if rev=='after' and ref['events']:unknown.append(key+':fixed_violation')
        for event in ref['events']:
            if rev!='before':continue
            fid=event['frame'];eid=f'{depth}/{policy}/frame{fid}';first=event['first']
            if first['ready']!=int(policy=='ready_first'):unknown.append(eid+':policy_not_exposed')
            targets[policy].add(eid)
            mapping.append(dict(evidence_id=eid,depth=depth,policy=policy,frame=fid,first_cycle=first['cycle'],
                first_ready=first['ready'],input_accept_cycles=[a['cycle'] for a in event['accepted']],
                output_handshake_cycles=[a['cycle'] for a in event['outputs']],leaked_beats=len(event['outputs']),
                obligation='oversize_frame_atomic_drop',origin='local development original RTL',independent=False))
    for depth in DEPTHS:
        for policy in POLICIES:
            before=refs.get(f'{depth}/{policy}/before');after=refs.get(f'{depth}/{policy}/after')
            witness=bool(before and after and before['events'] and not after['events'] and not(before['unknown'] or after['unknown']))
            pairs.append(dict(depth=depth,policy=policy,original_pair_witness=witness,
                              before_target_frames=len(before['events']) if before else None,
                              fixed_target_frames=len(after['events']) if after else None,
                              result='witness' if witness else 'no_exposure' if before and after and not(before['unknown'] or after['unknown']) else 'unknown'))
    matrix=[];detections={}
    for name,labels in CONTROLS.items():
        detected=set();triggered=set();fps=[];unresolved=[]
        for key,ref in refs.items():
            depth,policy,rev=key.split('/');r=native[key]
            def markers(which):
                result=set()
                for item in r[which]:
                    cy=re.search(r'cycle=(\d+)',item['detail'])
                    if not cy:unresolved.append(key+':missing_marker_cycle');continue
                    result.add((item['id'],int(cy[1])))
                return result
            triggers=markers('triggers');alarms=markers('failures')
            bycycle={ev['first']['cycle']:f'{depth}/{policy}/frame{ev["frame"]}' for ev in ref['events']}
            for label,cy in triggers:
                if label in labels and rev=='before' and cy in bycycle:triggered.add(bycycle[cy])
            for label,cy in alarms:
                if label not in labels:continue
                if (label,cy) not in triggers:unresolved.append(key+':alarm_without_trigger')
                elif cy in ref['correct_first_cycles']:fps.append(dict(key=key,label=label,cycle=cy))
                elif cy in bycycle and rev=='before':detected.add(bycycle[cy])
                else:unresolved.append(f'{key}:{label}:{cy}:unresolved_alarm')
        detections[name]=detected
        public=targets['ready_first'];history=targets['stalled_first']
        O=bool(public) and not(unknown or unresolved or fps or public-detected or public-triggered)
        H=O and bool(history) and not(history-detected or history-triggered)
        matrix.append(dict(candidate=name,origin='handwritten_local_control',editable=True,labels=labels,
            public_total=len(public),public_detected=len(public&detected),historical_total=len(history),historical_detected=len(history&detected),
            detected_ids=sorted(detected),missed_ids=sorted((public|history)-detected),missing_trigger_ids=sorted((public|history)-triggered),
            false_positive_records=fps,critical_unknown=unknown+unresolved,ordinary_accept=O,historical_accept=H))
    byname={v['candidate']:v for v in matrix};baseline=byname['partial_stalled'];replacement=byname['replacement_ready']
    protected=detections['partial_stalled'];lost=protected-detections['replacement_ready']
    qualified=bool(protected and targets['ready_first'] and not(detections['partial_stalled']&targets['ready_first']) and
        not(baseline['false_positive_records'] or baseline['critical_unknown']) and replacement['ordinary_accept'] and not replacement['historical_accept'] and lost and
        byname['union']['historical_accept'] and byname['full']['historical_accept'] and byname['overbroad']['false_positive_records'] and not byname['vacuous']['ordinary_accept'])
    s.dump(report/'candidate_matrix.json',matrix);s.dump(report/'pair_exposure.json',pairs);s.dump(report/'obligation_evidence_mapping.json',mapping)
    s.dump(report/'coverage_difference.json',dict(public_targets=sorted(targets['ready_first']),historical_targets=sorted(targets['stalled_first']),
        same_false_positive_and_unknown_guard=True,common_reference_and_RTL=True,
        public_semantics='First output presentation has ready=1; all bytes of that frame counted once.',
        historical_semantics='First output presentation has ready=0; later handshake corroborates early detection; subsequent ready beats not a second target.',
        local_replacement_lost=sorted(lost),retained_if_rejected=sorted(protected),
        fixed_components_excluding_regression=False,H_R_equivalent=True,real_model_extra_rejections=0,real_recoveries=0))
    decision=dict(local_structural_qualification=qualified,
        action='ELIGIBLE_FOR_LOCAL_CONTROLLER_AND_FRESH_SPACE_AUDIT' if qualified else 'STOP_NO_QUALIFIED_PARTIAL_CANDIDATE',
        model_pilot_sealed=False,model_calls=0,new_real_model_versions=0,new_independent_tests=0,
        conditional_recovery=dict(numerator=0,denominator=0,estimate=None),
        limits='Handwritten first-presentation partial checker; constrained unique-TID monitor. Multiple depths/ready contexts of one root defect, not independent bugs. No R-over-H claim. Fresh independent semantic target space and model interface/controller qualification not yet established.',
        next='Only if structural qualification holds: local interface/control branches and unused semantic target capacity before any model pilot or budget request. Otherwise stop. All new evidence is development-known.')
    s.dump(report/'decision.json',decision)
    s.dump(report/'cost.json',dict(model_calls=0,tokens=0,formal_calls=0,native_compile_attempts=len(jobs),native_executions=sum(j['result']['native_simulation_calls'] for j in jobs),
        compile_seconds=sum(j['result']['compile']['wall_seconds'] for j in jobs),execution_seconds=sum(j['result'].get('execute',{}).get('wall_seconds',0) for j in jobs)))
    s.dump(report/'checks.json',checks)
    lines=['# research185 同步FIFO丢帧：本地部分保护资格','',
           '**本地结构资格成立。未封存模型先导，未调用模型。**' if qualified else '**本地结构资格未成立，停止，不封存模型先导。**','',
           '|本地候选|公共目标检出|历史目标检出|误报记录|关键unknown|O/H|','|---|---|---|---|---|---|']
    for v in matrix:lines.append(f"|{v['candidate']}|{v['public_detected']}/{v['public_total']}|{v['historical_detected']}/{v['historical_total']}|{len(v['false_positive_records'])}|{len(v['critical_unknown'])}|{v['ordinary_accept']}/{v['historical_accept']}|")
    lines+=['', '固定Depth8/16/32 × 首次呈现就绪/背压两类场景，共6对原始RTL执行；各版本同时测6个手写控制集合。ID_ENABLE=1为原设计支持配置；帧ID在复位期间外不复用，ID与payload关联由实际握手复核。候选没有周期号、帧号或payload白名单，全部性质可编辑。',
        '', '部分候选仅检查首拍背压时的已接受帧长度/完成状态，遗漏首拍就绪事务；替换候选只检查首拍就绪时，因首拍已被观察，之后解除背压不再触发首次呈现性质。每个输入帧只计一个目标，泄漏多拍、提前检出和后来握手不重复计数。它们是同一历史修复的不同事务上下文，不是新独立Bug。',
        '', '普通规则检查公共目标及全部场景两版RTL上的合法误报/unknown；历史规则额外保持旧目标检出和触发。对照差别来自输出首拍就绪状态，不依赖样本白名单。联合/完整性质是手写正对照，不算模型恢复。固定版本必须满足独立原始端口参考，监视器不能自证正确。',
        '', '首拍输出的违例只有在后续实际握手归属同一超长帧时才确认为有效提前检出；未握手、映射不明、完成缺失及监视器不一致均unknown。合法帧保持完整；复位仅作为每场景初始化，本轮不验证复杂复位取消。参数/候选之外的行为不作全局保证。',
        '', f'本轮未知记录{len(unknown)}；局部检查{len(checks)}项通过。模型/网络/形式化调用0，12次原生编译预算，实际成本见cost.json。未读取旧独立测试或归档模型成功性质，旧记录不变。',
        '', '条件恢复仍0/0不可估计；H/R等价；576次搜索负结果保持。新目标属于开发已知证据，不能在未来搜索比较中重新计新发现。',
        '', '若资格成立，下一步仅可先做新接口/控制器分支及未使用独立语义空间核查，再决定是否封存有界模型先导。本轮没有调用授权申请。',
        '', '本地复现（新输出目录）：','```powershell','wsl -- python3 scripts/research185_drop_partial.py --out deliverables/research185_reproduce','```']
    (report/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    s.dump(report/'read_audit.json',dict(source_reads=sorted(str(p) for p in seen),denied_reads=denied,independent_contents_read=False,model_calls=0))
    bindings={s.rel(p):s.sha(p) for p in seen if p.is_file()}
    bindings[s.rel(Path(__file__))]=s.sha(Path(__file__))
    s.dump(report/'source_bindings.json',bindings)
    s.dump(report/'seal.json',{p.name:s.sha(p) for p in report.iterdir() if p.is_file()})
    print('RESULT185',json.dumps(decision),flush=True)


if __name__=='__main__':
    sys.dont_write_bytecode=True
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    execute(parser.parse_args().out.resolve())
