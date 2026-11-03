"""Local development qualification only. No model, pilot, or holdout evaluation.

Handwritten editable controls are deliberately distinguished from real proposals.
All controls share the original RTL and one passive event/count monitor.
"""
import argparse
from collections import Counter
from pathlib import Path
import re
import research177_history_screen as s

ROOT=s.ROOT
PREV=ROOT/'deliverables/research177_history_prepare_20261029_r03'
RUN=ROOT/'deliverables/research177_history_run_20261029_r01'
dump=s.dump
CATALOG={
    'partial_adjacent':['valid_check','adjacent_length'],
    'replacement_separated':['valid_check','separated_length'],
    'union':['valid_check','adjacent_length','separated_length'],
    'full_length':['valid_check','all_length'],
    'overbroad_single_beat':['valid_check','single_beat_length'],
    'vacuous':['valid_check','never_length'],
}


def bench(keep,rows):
    width,kw=(32,4) if keep else (8,1)
    lines=['module tb;bit clk=0;always #5 clk=~clk;bit rst=1;integer cycle=-1;',
        f'bit [{kw-1}:0] monitor_axis_tkeep;bit monitor_axis_tvalid=0,monitor_axis_tready=0,monitor_axis_tlast=0;wire [15:0] frame_len;wire frame_len_valid;',
        f'axis_frame_len #(.DATA_WIDTH({width}),.KEEP_ENABLE({keep}),.KEEP_WIDTH({kw})) dut(.*);',
        'wire accept=monitor_axis_tvalid && monitor_axis_tready;wire finish=accept && monitor_axis_tlast;',
        'integer acc_bytes=0;bit prev_complete=0;',
        'wire [31:0] beat_bytes='+('$countones(monitor_axis_tkeep)' if keep else "32'd1")+';',
        'always @(posedge clk) begin if(rst) begin acc_bytes<=0;prev_complete<=0;end else begin prev_complete<=finish;if(accept) begin if(monitor_axis_tlast) acc_bytes<=0;else acc_bytes<=acc_bytes+beat_bytes;end end end']
    conditions={'adjacent_length':'finish && prev_complete',
        'separated_length':'finish && !prev_complete','all_length':'finish',
        'single_beat_length':'finish','never_length':'finish && acc_bytes<0',
        'valid_check':"1'b1"}
    for label,antecedent in conditions.items():
        consequent=('frame_len_valid == $past(finish)' if label=='valid_check' else
            'frame_len_valid && frame_len == $past(beat_bytes)' if label=='single_beat_length' else
            'frame_len_valid && frame_len == $past(acc_bytes+beat_bytes)')
        lines += [f'{label}: assert property (@(posedge clk) disable iff(rst) ({antecedent}) |=> ({consequent})) else $display("ASSERT_FAIL {label} cycle=%0d",$sampled(cycle));',
            f'always @(posedge clk) if(!rst && ({antecedent})) $display("TRIGGER {label} cycle=%0d",cycle);']
    lines+=['initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for row in rows:
        k=row['k'] if keep else 1
        lines += [f"@(negedge clk);cycle={row['cycle']};rst={row['rst']};monitor_axis_tvalid={row['v']};monitor_axis_tready={row['r']};monitor_axis_tkeep={k};monitor_axis_tlast={row['last']};",
            '@(posedge clk);$display("TRACE cycle=%0d rst=%0d v=%0d r=%0d k=%0d last=%0d length=%0d valid=%0d acc=%0d prev=%0d",cycle,rst,monitor_axis_tvalid,monitor_axis_tready,monitor_axis_tkeep,monitor_axis_tlast,frame_len,frame_len_valid,acc_bytes,prev_complete);']
    return '\n'.join(lines+['@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'])


def seal(out):
    dump(out/'seal.json',{p.relative_to(out).as_posix():s.sha(p) for p in out.rglob('*') if p.is_file() and p.name!='seal.json'})


def prepare(out):
    s.verify(PREV)
    out.mkdir(parents=True,exist_ok=False)
    rows=s.read(PREV/'frame_stimuli.json')
    dump(out/'protocol.json',dict(
        stage='local_development_qualification_not_model_pilot',models=0,network=0,
        population=['pipeline_offbyone','frame_len_consecutive'],
        source_population='research177 fixed original history population; no new outcome-based case substitution',
        configs=[0,1],stimulus='unchanged research177 development stimuli',
        native_compile_budget=4,native_execution_budget=4,retries=0,
        ordinary='Same complete native execution, legal-source validation, all reference-correct samples guarded against false positives, completion-valid checks, and all separated-completion target transactions detected with actual antecedent samples. Unknown rejects.',
        historical='Ordinary rule plus preservation of the partial_adjacent baseline detections on adjacent-completion target transactions. Same executable and legal guards; no input-value/sample-ID whitelist.',
        roles='Adjacent means previous CLOCK also accepted TLAST; separated includes idle, stalled or multi-beat separation. Partition defined from accepted input events, not observed output or candidate outcome. All frame-length properties and valid_check editable; passive counter has no assert/veto.',
        qualification='Partial baseline has old detections and other wholly undetected transactions; replacement passes O and fails H for lost old detections; union passes both, with zero reference-correct false alarms and no critical unknown. Handwritten controls establish distinguishability only.',
        pipeline_scope='Audit all existing development diagnostic hold properties; no historical violation detection means ineligible. Frame-boundary error and later drain failure of the SAME loss trace are not independent current/historical targets.',
        isolation='Only research177 original source/development evidence. research174/175 and all independent results excluded.',
        stopping='Fixed four native jobs; tool failure stops execution, no replacement run. No model pilot/request/budget authorization generated.',
        limitations='Finite simulation, one frame-length root mechanism split by temporal context; not two bugs or contract-search new discoveries. H/R equivalent. Conditional real model recovery remains 0/0.'))
    dump(out/'candidate_catalog.json',CATALOG)
    dump(out/'stimuli.json',rows)
    for cfg in [0,1]:(out/f'tb_{cfg}.sv').write_text(bench(cfg,rows))
    paths=[Path(__file__),Path(s.__file__),Path(s.n.__file__),PREV/'seal.json',PREV/'source_manifest.json',RUN/'paired_results.json']
    for cfg in [2,3,4]:
        for rev in ['before','after']:
            paths.extend(RUN/'pipeline_offbyone'/str(cfg)/rev/x for x in ['result.json','execute.log','tb.sv'])
    for rev in ['before','after']:paths.append(PREV/'frame_len_consecutive'/rev/'axis_frame_len.v')
    dump(out/'bindings.json',{s.rel(p):s.sha(p) for p in paths})
    seal(out)
    print('PREPARED178 fixed four native jobs; no model pilot',flush=True)


def verify(prep):
    for key,value in s.read(prep/'seal.json').items():assert s.sha(prep/key)==value,key
    for key,value in s.read(prep/'bindings.json').items():assert s.sha(ROOT/key)==value,key
    s.verify(PREV)


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False);records=[]
    for cfg in [0,1]:
        for rev in ['before','after']:
            p=out/str(cfg)/rev
            r=s.n.run_native((prep/f'tb_{cfg}.sv').read_text(),p,
                extra_sources=[PREV/'frame_len_consecutive'/rev/'axis_frame_len.v'])
            records.append(dict(config=cfg,revision=rev,path=s.rel(p),result=r))
            dump(out/'executions.json',records)
            print('NATIVE178',cfg,rev,r['compile_status'],r['execution_status'],flush=True)
            if r['compile_status']!='passed' or r['execution_status']!='completed':break
        else:continue
        break
    dump(out/'cost.json',dict(model_calls=0,network_calls=0,formal_queries=0,
        native_compiles=len(records),native_executions=sum(r['result']['native_simulation_calls'] for r in records),
        compile_seconds=sum(r['result']['compile']['wall_seconds'] for r in records),
        execution_seconds=sum(r['result'].get('execute',{}).get('wall_seconds',0) for r in records),
        note='Six handwritten controls batched into each executable; no per-control cost inflation. Prior pipeline runs reused read-only.'))
    seal(out)


def marker_map(result,key):
    return {(x['id'],int(re.search(r'cycle=(\d+)',x['detail']).group(1))) for x in result.get(key,[])}


def independent_events(tr,cfg):
    """Group raw accepted inputs; never consult assertion predicates/results."""
    frames=[];pending=[];cancelled=[];last_completion=None;prev=None
    for i,v in enumerate(tr):
        if prev and not v['rst'] and not prev['rst'] and prev['v'] and not prev['r']:
            assert v['v'] and (v['k'],v['last'])==(prev['k'],prev['last']),'illegal source'
        if v['rst']:
            if pending:cancelled.append(dict(cycle=v['cycle'],accepted=pending))
            pending=[];last_completion=None;prev=v;continue
        assert v['acc']==sum(x['bytes'] for x in pending),'passive counter mismatch'
        assert bool(v['prev'])==(last_completion==v['cycle']-1),'passive timing mismatch'
        if v['v'] and v['r']:
            pending.append(dict(cycle=v['cycle'],bytes=v['k'].bit_count() if cfg else 1))
            if v['last']:
                check=tr[i+1] if i+1<len(tr) else None
                context='adjacent' if last_completion==v['cycle']-1 else 'separated'
                expected=sum(x['bytes'] for x in pending)
                status='unknown' if check is None or check['rst'] else 'pass' if check['valid'] and check['length']==expected else 'violation'
                frames.append(dict(anchor_cycle=v['cycle'],check_cycle=check['cycle'] if check else None,
                    accepted=pending,context=context,expected_length=expected,observed=check,
                    status=status,beat_bytes=pending[-1]['bytes']))
                pending=[];last_completion=v['cycle']
        prev=v
    return frames,cancelled


def audit(prep,run_dir,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False)
    for k,h in s.read(run_dir/'seal.json').items():assert s.sha(run_dir/k)==h,k
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:dump(out/'checks.json',checks);raise AssertionError(name)
    records=s.read(run_dir/'executions.json');check('all four original RTL jobs completed',len(records)==4)
    rows=[];native=[];pairs={}
    for rec in records:
        cfg,rev=rec['config'],rec['revision'];r=rec['result'];tr=s.trace(ROOT/rec['path'])
        check(f'{cfg}/{rev} native complete',r['compile_status']=='passed' and r['execution_status']=='completed')
        frames,cancelled=independent_events(tr,cfg);fails=marker_map(r,'failures');triggers=marker_map(r,'triggers')
        expected_fails=set();expected_triggers=set()
        for v in tr:
            if not v['rst']:expected_triggers.add(('valid_check',v['cycle']))
        for a,b in zip(tr,tr[1:]):
            if not a['rst'] and not b['rst'] and bool(b['valid'])!=bool(a['v'] and a['r'] and a['last']):expected_fails.add(('valid_check',b['cycle']))
        for f in frames:
            check(f'{cfg}/{rev}/{f["anchor_cycle"]} complete response',f['status']!='unknown')
            labels=['all_length','single_beat_length',f['context']+'_length']
            for label in labels:
                expected_triggers.add((label,f['anchor_cycle']))
                wanted=f['beat_bytes'] if label=='single_beat_length' else f['expected_length']
                if not f['observed']['valid'] or f['observed']['length']!=wanted:expected_fails.add((label,f['check_cycle']))
            rows.append(dict(config=cfg,revision=rev,**f))
        check(f'{cfg}/{rev} exact native failure reconciliation',fails==expected_fails)
        check(f'{cfg}/{rev} exact antecedent marker reconciliation',triggers==expected_triggers)
        check(f'{cfg}/{rev} reset cancellation exercised',bool(cancelled))
        oracle=s.oracle_frame(tr,cfg);check(f'{cfg}/{rev} independent input legality',oracle['legal'])
        native.append(dict(config=cfg,revision=rev,failures=sorted(fails),triggers=sorted(triggers),cancelled=cancelled))
        pairs[cfg,rev]=(tr,frames,fails,triggers)
    for cfg in [0,1]:
        a,b=pairs[cfg,'before'][0],pairs[cfg,'after'][0]
        check(f'{cfg} identical raw port stimulus',[[v[k] for k in ['rst','v','r','k','last']] for v in a]==[[v[k] for k in ['rst','v','r','k','last']] for v in b])
        check(f'{cfg} fixed satisfies every frame',all(f['status']=='pass' for f in pairs[cfg,'after'][1]))
    decisions=[]
    for candidate,labels in CATALOG.items():
        old_total=current_total=old_hit=current_hit=false_alarm=unknown=missing_trigger=0
        for (cfg,rev),(tr,frames,fails,triggers) in pairs.items():
            selected={cy for label,cy in fails if label in labels}
            oracle=s.oracle_frame(tr,cfg)
            actual_bad={f['cycle'] for f in oracle['failures']}
            false_alarm+=len(selected-actual_bad)
            for f in frames:
                if f['status']=='unknown':unknown+=1;continue
                if rev!='before' or f['status']!='violation':continue
                hit=f['check_cycle'] in selected
                if f['context']=='adjacent':old_total+=1;old_hit+=hit
                else:
                    current_total+=1;current_hit+=hit
                    missing_trigger+=not any((label,f['anchor_cycle']) in triggers for label in labels if label!='valid_check')
        ordinary=bool(current_total and current_hit==current_total and not(false_alarm or unknown or missing_trigger))
        historical=ordinary and old_total>0 and old_hit==old_total
        decisions.append(dict(candidate=candidate,origin='handwritten local control, not model output',labels=labels,
            history_targets=old_total,history_detected=old_hit,current_targets=current_total,current_detected=current_hit,
            false_alarm_samples=false_alarm,critical_unknown=unknown,current_missing_trigger=missing_trigger,
            ordinary_accept=ordinary,history_accept=historical,
            decision_reason='current targets + all reference-correct sample guards + current triggers; H additionally preserves adjacent detections'))
    dec={x['candidate']:x for x in decisions}
    base=dec['partial_adjacent'];replace=dec['replacement_separated']
    check('partial baseline real protection and real misses',base['history_detected']==6 and base['current_detected']==0 and not base['false_alarm_samples'])
    check('replacement O accept H extra reject',replace['ordinary_accept'] and not replace['history_accept'] and replace['history_detected']==0)
    check('union control restores both classes',dec['union']['ordinary_accept'] and dec['union']['history_accept'])
    check('overbroad rule rejected for genuine legal false alarms',dec['overbroad_single_beat']['false_alarm_samples']>0 and not dec['overbroad_single_beat']['ordinary_accept'])
    check('vacuous rule rejected for missing targets and triggers',not dec['vacuous']['ordinary_accept'] and dec['vacuous']['current_missing_trigger']==2)
    # Audit existing pipeline evidence rather than inventing a second bug from later symptoms.
    pipeline=[]
    for cfg in [2,3,4]:
        for rev in ['before','after']:
            p=RUN/'pipeline_offbyone'/str(cfg)/rev;r=s.read(p/'result.json');tr=s.trace(p);o=s.oracle_pipe(tr)
            check(f'pipeline/{cfg}/{rev} original complete',r['execution_status']=='completed' and o['legal'])
            check(f'pipeline/{cfg}/{rev} diagnostic has no target detection',not r['failures'])
            pipeline.append(dict(config=cfg,revision=rev,oracle_failures=o['failures'],accepted=o['accepted'],returned=o['returned'],
                candidate_failures=r['failures'],trigger_markers=len(r['triggers']),path=s.rel(p)))
    matrix=[dict(case='pipeline_offbyone',source_and_pair='verified research177 original pair',
        candidate='existing hold_valid + hold_data',editable=True,old_target_detections=0,current_missed_loss_traces=2,
        non_whitelist_discrimination='not established',qualified=False,
        reason='Stall property triggers are not old error detections. Frame-boundary and drain symptoms of the same undetected loss do not create separate historical/current transactions. No new fault is injected to force qualification.'),
        dict(case='frame_len_consecutive',source_and_pair='verified original pair in both configurations',
        candidate='partial_adjacent',editable=True,old_target_detections=base['history_detected'],current_missed_targets=base['current_targets'],
        non_whitelist_discrimination='input completion adjacency versus temporal separation; replacement O accepted/H rejected',qualified=True,
        reason='Local structural qualification only; all properties editable. Same root count-carryover defect, distinct frame transactions and temporal contexts; counts are not independent bugs. No real model recovery or prospective value established.')]
    dump(out/'candidate_qualification_matrix.json',matrix);dump(out/'all_control_decisions.json',decisions)
    dump(out/'frame_transactions.json',rows);dump(out/'native_reconciliation.json',native);dump(out/'pipeline_audit.json',pipeline)
    dump(out/'checks.json',checks);dump(out/'cost.json',s.read(run_dir/'cost.json'))
    dump(out/'provenance.json',dict(prepared=s.rel(prep),run=s.rel(run_dir),prepared_seal=s.sha(prep/'seal.json'),run_seal=s.sha(run_dir/'seal.json'),
        independent_data_read=False,pilot_sealed=False,model_calls=0,conditional_model_recovery={'numerator':0,'denominator':0,'estimate':None},
        previous_version_retention='Local decision records reject replacement and retain partial_adjacent unchanged; no deployed candidate changed. Union is a handwritten positive control, NOT a recovery result.'))
    report='''# research178 本地部分保护资格检查

两个原始历史案例中，frame_len通过本地结构资格；pipeline_fifo在现有开发材料上不成立。未调用模型、未封存模型先导，没有自动恢复成功。

|案例|已有历史目标检出|当前漏报|可编辑／非白名单区分|结论|
|---|---|---|---|---|
|axis_pipeline_fifo off-by-one|0；保持断言虽触发但未报任何目标错误|LENGTH=2、4各一个原始丢失轨迹|性质可编辑；未建立实质区分|停止本案例先导准备；不能把同一次丢失的帧边界和后续排空症状拆成新旧独立目标|
|axis_frame_len consecutive|6个相邻完成帧违例点被部分候选检出|2个间隔完成帧违例点未检出，长度性质未触发|性质全部可编辑；按输入握手完成是否相邻分类|通过本地资格，尚非真实模型增量证据|

所有新候选均为明确标注的手写本地对照。复用research177开发激励，分别在KEEP关闭8位、KEEP启用32位的原始前后RTL上执行；每版8个完成帧。原版各4个长度错误，修复版均正确。新部分候选保留连续帧保护，遗漏有空闲/背压间隔的帧；参考计数独立从实际输入握手组帧，逐项核对原生断言和监视器。

普通规则检查当前间隔帧目标、全部参考正确采样上的误报、完成有效标志和必要触发；历史规则另外要求旧相邻帧目标继续检出。没有按周期号、KEEP值或样本ID写白名单，也没有固定不可编辑的历史保护性质。分类依据此前一时钟是否接受TLAST，涵盖完整时间类；这是待修与历史行为的明确范围划分，不是普通规则全功能正确性的声明。

替换为间隔帧性质的手写对照：普通接受、历史额外拒绝（丢失6个旧检出），保留原部分候选；联合性质同时通过。过宽的“所有帧都只有一拍”对照因合法多拍帧误报被拒绝；空前件对照因漏报及缺触发被拒绝。联合对照不计作模型恢复成功；本轮所有采样都是开发数据，已知缺口不能再算搜索新增发现。

新断言只使用通用握手/计数监视器，无预存答案表、事件编号或原始DUT内部信号。触发由与原生前件一致的采样标记复核，不是形式化覆盖证明。范围不含稀疏KEEP、16位计数溢出、多时钟或其他模块。

下一步仅frame_len值得继续本地检查：确认新的独立语义样本余量，并将此接口和两种规则接入预算控制器，验证分支后再另行封存先导。当前没有请求预览或模型预算授权；pipeline资格不足不应靠追加调用弥补。

H/R等价限制不变；真实条件恢复仍0/0不可估计。576次搜索无独有收益结果、所有既有独立结果和旧失败均保持不变。
'''
    report+=f'\n本轮{len(checks)}项审计通过；4次原生编译/执行，六组性质并行记录但不重复计成本。命令、工具版本、逐周期日志及波形位于 `{s.rel(run_dir)}`。模型/网络/形式化均0。\n'
    (out/'SUMMARY.md').write_text(report,encoding='utf-8');seal(out)
    print('AUDITED178',len(checks),'checks; frame qualified, pipeline not qualified',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','audit']);p.add_argument('--prepared');p.add_argument('--run');p.add_argument('--out',required=True);a=p.parse_args()
    if a.action=='prepare':prepare(Path(a.out).resolve())
    elif a.action=='run':run(Path(a.prepared).resolve(),Path(a.out).resolve())
    else:audit(Path(a.prepared).resolve(),Path(a.run).resolve(),Path(a.out).resolve())
